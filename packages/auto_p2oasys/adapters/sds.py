"""
SDS (Safety Data Sheet) adapter for auto_p2oasys.

Parses SDS PDFs to extract CAS numbers, flash point, vapor pressure, and
other hazard data from Section 9 (Physical Properties) and other sections.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..evidence import Evidence
from ..source_report import SourceReport, AdapterStatus
from ..cas_utils import extract_cas_from_text, format_cas_display


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

    text = _extract_text(sds_path)
    if not text:
        if report:
            report.add("sds_extract", AdapterStatus.ERROR, "Could not extract text")
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


def parse_sds(sds_path: Path, cas: str) -> list[Evidence]:
    """
    Parse SDS PDF and extract evidence for a specific CAS.

    Focuses on Section 9 (Physical Properties) for flash point, vapor pressure,
    boiling point, etc.

    Args:
        sds_path: Path to SDS PDF file
        cas: CAS number to associate with evidence

    Returns:
        List of Evidence records extracted
    """
    if not sds_path.exists():
        return []

    text = _extract_text(sds_path)
    if not text:
        return []

    display_cas = format_cas_display(cas)
    now = datetime.now(timezone.utc)
    evidence: list[Evidence] = []

    section_9 = _extract_section(text, "9")

    if section_9:
        flash = _parse_flash_point(section_9)
        if flash is not None:
            evidence.append(
                Evidence(
                    cas=display_cas,
                    endpoint="flash_point",
                    value=flash["value"],
                    unit=flash.get("unit", "°C"),
                    qualifier=flash.get("qualifier"),
                    source="SDS",
                    predicted=False,
                    section="Section 9",
                    raw_text=flash.get("raw"),
                    retrieved_at=now,
                )
            )

        vp = _parse_vapor_pressure(section_9)
        if vp is not None:
            evidence.append(
                Evidence(
                    cas=display_cas,
                    endpoint="vapor_pressure",
                    value=vp["value"],
                    unit=vp.get("unit", "mmHg"),
                    source="SDS",
                    predicted=False,
                    section="Section 9",
                    raw_text=vp.get("raw"),
                    retrieved_at=now,
                )
            )

        bp = _parse_boiling_point(section_9)
        if bp is not None:
            evidence.append(
                Evidence(
                    cas=display_cas,
                    endpoint="boiling_point",
                    value=bp["value"],
                    unit=bp.get("unit", "°C"),
                    source="SDS",
                    predicted=False,
                    section="Section 9",
                    raw_text=bp.get("raw"),
                    retrieved_at=now,
                )
            )

    section_2 = _extract_section(text, "2")
    if section_2:
        h_codes = re.findall(r"\bH\d{3}[A-Z]?\b", section_2)
        if h_codes:
            evidence.append(
                Evidence(
                    cas=display_cas,
                    endpoint="h_codes",
                    value=list(set(h_codes)),
                    source="SDS",
                    predicted=False,
                    section="Section 2",
                    retrieved_at=now,
                )
            )

    return evidence


def _extract_text(path: Path) -> str:
    """Extract text from PDF using available libraries."""
    try:
        import pdfplumber

        with pdfplumber.open(path) as pdf:
            text_parts = []
            for page in pdf.pages:
                text = page.extract_text() or ""
                text_parts.append(text)
            return "\n".join(text_parts)
    except ImportError:
        pass
    except Exception:
        pass

    try:
        from pypdf import PdfReader

        reader = PdfReader(path)
        text_parts = []
        for page in reader.pages:
            text = page.extract_text() or ""
            text_parts.append(text)
        return "\n".join(text_parts)
    except ImportError:
        pass
    except Exception:
        pass

    return ""


def _extract_section(text: str, section_num: str) -> str | None:
    """Extract a specific section from SDS text."""
    pattern = rf"(?:SECTION\s*{section_num}|{section_num}\.\s*\w)"
    parts = re.split(pattern, text, flags=re.IGNORECASE)

    if len(parts) < 2:
        return None

    section_text = parts[1]

    next_section = re.search(
        rf"(?:SECTION\s*{int(section_num) + 1}|\n{int(section_num) + 1}\.\s*\w)",
        section_text,
        flags=re.IGNORECASE,
    )
    if next_section:
        section_text = section_text[: next_section.start()]

    return section_text[:5000]


def _parse_flash_point(text: str) -> dict | None:
    """Parse flash point from text."""
    patterns = [
        r"flash\s*point[:\s]*([<>≈~]?\s*[-−]?\d+\.?\d*)\s*°?\s*([CF])",
        r"flash\s*point[:\s]*([<>≈~]?\s*[-−]?\d+\.?\d*)\s*(celsius|fahrenheit)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            val_str = match.group(1).strip()
            unit = match.group(2).upper()

            qualifier = None
            if val_str[0] in "<>≈~":
                qualifier = val_str[0]
                val_str = val_str[1:].strip()

            try:
                value = float(val_str.replace("−", "-"))
                if unit == "F" or "fahrenheit" in unit.lower():
                    value = (value - 32) * 5 / 9
                    unit = "°C"
                else:
                    unit = "°C"

                return {
                    "value": round(value, 1),
                    "unit": unit,
                    "qualifier": qualifier,
                    "raw": match.group(0),
                }
            except ValueError:
                pass

    return None


def _parse_vapor_pressure(text: str) -> dict | None:
    """Parse vapor pressure from text."""
    patterns = [
        r"vapor\s*pressure[:\s]*([<>≈~]?\s*\d+\.?\d*)\s*(mmHg|mm\s*Hg|hPa|kPa|mbar|atm)",
        r"vapour\s*pressure[:\s]*([<>≈~]?\s*\d+\.?\d*)\s*(mmHg|mm\s*Hg|hPa|kPa|mbar|atm)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            val_str = match.group(1).strip()
            unit = match.group(2).lower()

            if val_str[0] in "<>≈~":
                val_str = val_str[1:].strip()

            try:
                value = float(val_str)

                if "hpa" in unit or "mbar" in unit:
                    value = value * 0.750062
                elif "kpa" in unit:
                    value = value * 7.50062
                elif "atm" in unit:
                    value = value * 760

                return {
                    "value": round(value, 2),
                    "unit": "mmHg",
                    "raw": match.group(0),
                }
            except ValueError:
                pass

    return None


def _parse_boiling_point(text: str) -> dict | None:
    """Parse boiling point from text."""
    patterns = [
        r"boiling\s*point[:\s]*([<>≈~]?\s*[-−]?\d+\.?\d*)\s*°?\s*([CF])",
        r"boiling\s*range[:\s]*([<>≈~]?\s*[-−]?\d+\.?\d*)\s*°?\s*([CF])",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            val_str = match.group(1).strip()
            unit = match.group(2).upper()

            if val_str[0] in "<>≈~":
                val_str = val_str[1:].strip()

            try:
                value = float(val_str.replace("−", "-"))
                if unit == "F":
                    value = (value - 32) * 5 / 9
                    unit = "°C"
                else:
                    unit = "°C"

                return {
                    "value": round(value, 1),
                    "unit": unit,
                    "raw": match.group(0),
                }
            except ValueError:
                pass

    return None
