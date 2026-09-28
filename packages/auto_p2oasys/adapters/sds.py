"""
SDS (Safety Data Sheet) adapter for auto_p2oasys.

Parses SDS PDFs to extract hazard data with full GHaz7-compatible structured parsing.
Supports both explicit uploads (--sds) and cache lookup (--sds-cache / TSCD_SDS_CACHE_DIR).

Ported from GHaz7 with offline-only support and bug fixes per PR #12 brief.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..evidence import Evidence
from ..source_report import SourceReport, AdapterStatus
from ..cas_utils import extract_cas_from_text, format_cas_display, validate_cas_checksum

from . import sds_text
from . import sds_structured
from . import sds_bridge
from . import sds_cache


@dataclass
class SDSParseOutcome:
    """Result of parsing an SDS document."""
    
    fields: dict = field(default_factory=dict)
    evidence: list = field(default_factory=list)
    unmapped: list = field(default_factory=list)
    mixture: dict | None = None
    meta: dict = field(default_factory=dict)
    error: str | None = None


@dataclass
class SDSMeta:
    """SDS document metadata."""
    
    path: Path | None = None
    vendor: str = "unknown"
    revision: str = ""
    sha256: str = ""
    n_pages: int = 0
    backend: str = ""
    sections_found: list = field(default_factory=list)
    file_name: str = ""
    is_mixture: bool = False
    mixture_reason: str = ""
    target_concentration: str = ""


def extract_cas_from_sds(
    sds_path: Path,
    report: SourceReport | None = None,
) -> list[str]:
    """
    Extract CAS numbers from an SDS PDF.

    Args:
        sds_path: Path to SDS PDF file
        report: Optional source report to record status

    Returns:
        List of valid CAS numbers found
    """
    if not sds_path.exists():
        if report:
            report.add("sds_extract", AdapterStatus.ERROR, "File not found")
        return []

    text, backend = sds_text.extract_text_from_pdf(sds_path)
    if not text:
        if report:
            report.add("sds_extract", AdapterStatus.ERROR, "Could not extract text")
        return []

    if sds_text.is_scanned_pdf(text):
        if report:
            report.add(
                "sds_extract",
                AdapterStatus.ERROR,
                "No text layer (scanned PDF?); OCR not supported offline",
            )
        return []

    cas_numbers = extract_cas_from_text(text)

    if report:
        if cas_numbers:
            report.add(
                "sds_extract",
                AdapterStatus.RAN,
                evidence_count=len(cas_numbers),
            )
        else:
            report.add("sds_extract", AdapterStatus.NO_DATA, "No CAS numbers found")

    return cas_numbers


def _extract_vendor_from_text(text: str) -> str:
    """Extract vendor/supplier name from SDS text."""
    patterns = [
        r"(?:Supplier|Manufacturer|Company)[:\s]+([^\n]{5,60})",
        r"(?:Distributed\s+by|Produced\s+by)[:\s]+([^\n]{5,60})",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            vendor = m.group(1).strip()
            vendor = re.sub(r"\s+", " ", vendor)
            vendor = vendor[:50]
            return vendor
    return "unknown vendor"


def _compute_sha256(path: Path) -> str:
    """Compute SHA256 hash of file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _detect_mixture(
    sections: dict[int, str],
    target_cas: str,
    full_text: str,
) -> tuple[bool, str, str]:
    """
    Detect if SDS is for a mixture/solution.
    
    Fix #2: Use "Substance / Mixture" line and TCI concentration format (">= 90 - <= 100").
    
    Returns:
        (is_mixture, reason, target_concentration)
    """
    sec1 = sections.get(1) or ""
    sec3 = sections.get(3) or ""
    
    substance_line = re.search(r"Substance\s*/\s*Mixture\s*[:\-]?\s*(\w+)", full_text, re.I)
    if substance_line:
        classification = substance_line.group(1).lower()
        if classification == "substance":
            return False, "", ">= 90%"
        elif classification == "mixture":
            return True, "Classified as Mixture in section 1", ""
    
    cas_pattern = re.compile(r"\b(\d{1,9}-\d{2}-\d)\b")
    cas_hits = cas_pattern.findall(sec3)
    
    valid_cas = []
    for cas in cas_hits:
        if validate_cas_checksum(cas):
            valid_cas.append(cas)
    
    unique_cas = list(dict.fromkeys(valid_cas))
    
    target_conc = None
    target_normalized = target_cas.replace("-", "")
    
    for cas in unique_cas:
        cas_norm = cas.replace("-", "")
        if cas_norm == target_normalized:
            tci_conc = re.search(
                rf"{re.escape(cas)}[^\n]{{0,80}}?(?:>=?\s*)?(\d+(?:\.\d+)?)\s*(?:-\s*(?:<=?\s*)?(\d+(?:\.\d+)?))?\s*%?",
                sec3, re.I,
            )
            if tci_conc:
                low = float(tci_conc.group(1))
                high = float(tci_conc.group(2)) if tci_conc.group(2) else low
                target_conc = (low, high)
    
    is_mixture = False
    reason = ""
    concentration = ""
    
    if len(unique_cas) >= 2:
        if target_conc and target_conc[1] < 90:
            is_mixture = True
            reason = f"Target CAS concentration {target_conc[0]}-{target_conc[1]}% < 90%"
            concentration = f"{target_conc[0]}-{target_conc[1]}%"
        elif not target_conc and len(unique_cas) >= 2:
            is_mixture = True
            reason = f"Multiple CAS numbers ({len(unique_cas)}) without concentration data"
    
    if target_conc:
        concentration = f"{target_conc[0]}%" if target_conc[0] == target_conc[1] else f"{target_conc[0]}-{target_conc[1]}%"
    
    return is_mixture, reason, concentration


def is_mixture_sds(path: Path, cas: str) -> bool:
    """
    Check if SDS is for a mixture/solution (fix #1: function was missing).
    
    Args:
        path: Path to SDS PDF file
        cas: Target CAS number
    
    Returns:
        True if mixture/solution detected
    """
    text, _ = sds_text.extract_text_from_pdf(path)
    if not text:
        return False
    
    sections = sds_text.split_sections(text)
    is_mixture, _, _ = _detect_mixture(sections, cas, text)
    return is_mixture


def _extract_revision_date(text: str) -> str:
    """Extract SDS revision date from text (section 1 or section 16)."""
    patterns = [
        r"Revision\s*(?:Date|date)[:\s]*([0-9]{1,2}[/\-][0-9]{1,2}[/\-][0-9]{2,4})",
        r"SDS\s*(?:Revision|revision)[:\s]*([0-9]{1,2}[/\-][0-9]{1,2}[/\-][0-9]{2,4})",
        r"Last\s*(?:Revised|Updated)[:\s]*([0-9]{1,2}[/\-][0-9]{1,2}[/\-][0-9]{2,4})",
        r"Date\s*(?:of\s+)?(?:Revision|Issue)[:\s]*([0-9]{1,2}[/\-][0-9]{1,2}[/\-][0-9]{2,4})",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            return m.group(1).strip()
    return ""


def parse_sds_document(
    path: Path,
    cas: str,
    *,
    vendor: str | None = None,
    revision: str | None = None,
    relative_path: str | None = None,
    include_mixture: bool = False,
) -> SDSParseOutcome:
    """
    Parse SDS PDF with full structured extraction.
    
    Args:
        path: Path to SDS PDF file
        cas: Target CAS number
        vendor: Override vendor name (from cache metadata)
        revision: Override revision date (from cache metadata)
        relative_path: Relative path in cache (for reference)
        include_mixture: Include mixture SDS values in scoring
    
    Returns:
        SDSParseOutcome with fields, evidence, unmapped, mixture info, and metadata
    """
    outcome = SDSParseOutcome()
    
    if not path.exists():
        outcome.error = "File not found"
        return outcome
    
    text, backend = sds_text.extract_text_from_pdf(path)
    
    if not text:
        outcome.error = "Could not extract text from PDF"
        return outcome
    
    if sds_text.is_scanned_pdf(text):
        outcome.error = "No text layer (scanned PDF?); OCR not supported offline"
        return outcome
    
    sha256 = _compute_sha256(path)
    n_pages = sds_text.get_n_pages(path)
    
    if vendor is None:
        vendor = _extract_vendor_from_text(text)
    
    if revision is None:
        revision = _extract_revision_date(text)
    
    sections = sds_text.split_sections(text)
    
    is_mixture, mixture_reason, target_conc = _detect_mixture(sections, cas, text)
    
    structured = sds_structured.parse_structured_sds(sections, full_text=text)
    
    fields = sds_bridge.structured_sds_to_extra_fields(structured)
    
    file_name = path.name
    source_label = f"SDS ({vendor}, {file_name})"
    
    ref_parts = [vendor]
    if revision:
        ref_parts.append(f"rev {revision}")
    if relative_path:
        ref_parts.append(relative_path)
    ref_parts.append(f"sha256:{sha256[:12]}")
    reference_str = ", ".join(ref_parts)
    
    evidence, unmapped = sds_bridge.sds_fields_to_evidence(
        fields,
        cas,
        source_label=source_label,
        vendor=vendor,
        revision=revision or "",
        file_name=file_name,
        reference=reference_str,
    )
    
    if is_mixture:
        for ev in evidence:
            if ev.reliability:
                new_reliability = f"{ev.reliability}; mixture/solution SDS: not pure-substance data"
            else:
                new_reliability = "mixture/solution SDS: not pure-substance data"
            evidence[evidence.index(ev)] = Evidence(
                cas=ev.cas,
                endpoint=ev.endpoint,
                value=ev.value,
                unit=ev.unit,
                qualifier=ev.qualifier,
                source=ev.source,
                source_type=ev.source_type,
                predicted=ev.predicted,
                reliability=new_reliability,
                reference=ev.reference,
                retrieved_at=ev.retrieved_at,
                section=ev.section,
                raw_text=ev.raw_text,
            )
    
    outcome.fields = fields
    outcome.evidence = evidence
    outcome.unmapped = unmapped
    outcome.mixture = {
        "is_mixture": is_mixture,
        "reason": mixture_reason,
        "target_concentration": target_conc,
    } if is_mixture else None
    outcome.meta = {
        "path": str(path),
        "vendor": vendor,
        "sha256": sha256[:12],
        "n_pages": n_pages,
        "backend": backend,
        "sections_found": list(sections.keys()),
        "file_name": file_name,
        "is_mixture": is_mixture,
        "mixture_reason": mixture_reason,
        "target_concentration": target_conc,
        "source_label": source_label,
    }
    
    return outcome


def parse_sds(
    sds_path: Path,
    cas: str,
    vendor: str | None = None,
) -> list[Evidence]:
    """
    Parse SDS PDF and extract evidence for a specific CAS.
    
    Backward-compatible wrapper around parse_sds_document.

    Args:
        sds_path: Path to SDS PDF file
        cas: CAS number to associate with evidence
        vendor: Override vendor name (from cache metadata)

    Returns:
        List of Evidence records extracted
    """
    outcome = parse_sds_document(sds_path, cas, vendor=vendor)
    
    if outcome.error:
        return []
    
    return outcome.evidence


def resolve_sds(
    cas: str,
    explicit_sds: Path | None = None,
    cache_dir: Path | None = None,
) -> tuple[Path | None, dict]:
    """
    Resolve SDS PDF path from explicit upload or cache.
    
    Args:
        cas: CAS registry number
        explicit_sds: Explicit --sds path (takes precedence)
        cache_dir: Override cache directory
    
    Returns:
        (path, meta) where meta has vendor, revision, sha256, candidates
    """
    if explicit_sds is not None:
        if explicit_sds.exists():
            sha256 = _compute_sha256(explicit_sds)
            vendor = "uploaded"
            return explicit_sds, {
                "vendor": vendor,
                "revision": "",
                "sha256": sha256[:12],
                "source": "explicit_upload",
                "candidates": [],
            }
        return None, {"error": f"File not found: {explicit_sds}"}
    
    hit = sds_cache.lookup_sds_in_cache(cas, cache_dir)
    if hit:
        return hit["path"], {
            "vendor": hit["vendor"],
            "revision": hit["revision"],
            "sha256": hit["sha256"][:12],
            "source": "cache",
            "relative_path": hit["relative_path"],
            "candidates": hit["candidates"],
        }
    
    if cache_dir is not None or sds_cache.get_cache_dir() is not None:
        cache_path = cache_dir or sds_cache.get_cache_dir()
        return None, {
            "error": f"SDS: none found in {cache_path} for CAS {cas}",
            "source": "cache_miss",
        }
    
    return None, {"source": "none_configured"}
