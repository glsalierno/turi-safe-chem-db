"""Read a user-uploaded SDS PDF into a DoSS row, only when the product CAS is clear.

Safety data sheets use different layouts and often list more than one CAS
(ingredients, impurities, or regulatory cross-references). Physical properties
on a mixture sheet describe the mixture, so those values are not copied onto
a single ingredient.
"""

from __future__ import annotations

import re
from io import BytesIO
from typing import Any, Optional

from packages.doss_core.tci import parse_sds_fields
from packages.p2oasys_core.lookup import format_cas_display, normalize_cas

SHARE_SDS_MESSAGE = (
    "If this safety data sheet did not upload or read correctly, please share "
    "the PDF with Gabriel so it can be kept as a reference."
)

_DASHES = str.maketrans(
    {
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
        "\u00ad": "",
    }
)

_SECTION = re.compile(
    r"(?im)(?:^|\n)\s*(?:SECTION[ \t]+)?(\d{1,2})[ \t]*[\.\:\)]?[ \t]*(?:\n\s*)?"
    r"(identification|hazard|composition|first\s+aid|fire|accidental|handling|"
    r"exposure|physical|stability|toxicolog\w*|ecological|disposal|transport|"
    r"regulatory|other(?:\s+information)?)\b"
)

_CAS = re.compile(
    r"(?<!\d)(\d{2,7})\s*-\s*(\d{2})\s*-\s*(\d)(?!\d)"
)

_PCT = re.compile(
    r"(?:>|≥|>=)?\s*(\d{1,3}(?:\.\d+)?)\s*(?:%|percent|wt\.?\s*%|w/w)",
    re.I,
)

_GENERIC_GLOVE = {
    "unknown",
    "-",
    "impervious gloves",
    "protective gloves",
    "appropriate protective gloves",
}


def cas_checksum_ok(left: str, mid: str, check: str) -> bool:
    """True when the last digit matches the CAS check-digit rule."""
    body = f"{left}{mid}"
    if not body.isdigit() or not check.isdigit():
        return False
    total = sum(i * int(ch) for i, ch in enumerate(reversed(body), start=1))
    return total % 10 == int(check)


def _pypdf_text(pdf_bytes: bytes) -> str:
    for mod_name in ("pypdf", "PyPDF2"):
        try:
            import importlib

            mod = importlib.import_module(mod_name)
            reader = mod.PdfReader(BytesIO(pdf_bytes))
            parts: list[str] = []
            for page in reader.pages[:15]:
                try:
                    parts.append(page.extract_text() or "")
                except Exception:
                    continue
            return "\n".join(parts)
        except Exception:
            continue
    return ""


def _pdfminer_text(pdf_bytes: bytes) -> str:
    try:
        from pdfminer.high_level import extract_text

        return extract_text(BytesIO(pdf_bytes), maxpages=15) or ""
    except Exception:
        return ""


def pdf_bytes_to_text(pdf_bytes: bytes) -> str:
    """Extract text from a text-based PDF. Scanned sheets return little or nothing."""
    if not pdf_bytes or not pdf_bytes.startswith(b"%PDF"):
        return ""
    primary = _pypdf_text(pdf_bytes)
    prepared = _prepare_text(primary)
    if len(prepared.strip()) >= 80 and _CAS.search(prepared):
        return primary
    alternate = _pdfminer_text(pdf_bytes)
    if len(alternate.strip()) > len(primary.strip()):
        return alternate
    return primary


def _prepare_text(text: str) -> str:
    cleaned = (text or "").translate(_DASHES)
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(r"-\s*\n\s*", "-", cleaned)
    return cleaned


def _sections(text: str) -> list[tuple[int, int, int]]:
    """Return (start, end, section_number) spans. 0 means no recognized header."""
    headers = list(_SECTION.finditer(text))
    if not headers:
        return [(0, len(text), 0)]
    spans: list[tuple[int, int, int]] = []
    if headers[0].start() > 0:
        spans.append((0, headers[0].start(), 0))
    for i, match in enumerate(headers):
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        spans.append((match.start(), end, int(match.group(1))))
    return spans


def _section_at(spans: list[tuple[int, int, int]], pos: int) -> int:
    for start, end, number in spans:
        if start <= pos < end:
            return number
    return 0


def _percent_near(text: str, start: int, end: int) -> Optional[float]:
    window = text[end : min(len(text), end + 80)]
    match = _PCT.search(window)
    if not match:
        return None
    try:
        value = float(match.group(1))
    except ValueError:
        return None
    if value < 0 or value > 100:
        return None
    return value


def find_cas_hits(text: str) -> list[dict[str, Any]]:
    """Checksum-valid CAS numbers, with SDS section and a nearby weight percent."""
    prepared = _prepare_text(text)
    spans = _sections(prepared)
    hits: list[dict[str, Any]] = []
    seen_at: set[tuple[str, int]] = set()
    for match in _CAS.finditer(prepared):
        left, mid, check = match.group(1), match.group(2), match.group(3)
        if not cas_checksum_ok(left, mid, check):
            continue
        cas = f"{int(left)}-{mid}-{check}"
        key = (cas, match.start())
        if key in seen_at:
            continue
        seen_at.add(key)
        section = _section_at(spans, match.start())
        hits.append(
            {
                "cas": cas,
                "section": section,
                "pos": match.start(),
                "percent": _percent_near(prepared, match.start(), match.end()),
            }
        )
    return hits


def _unique(hits: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for hit in hits:
        if hit["cas"] not in out:
            out.append(hit["cas"])
    return out


def _format_list(cas_numbers: list[str]) -> str:
    return ", ".join(format_cas_display(c) for c in cas_numbers)


def review_sds_text(
    text: str,
    *,
    requested_cas: str = "",
    filename: str = "",
) -> dict[str, Any]:
    """Decide whether an SDS text is safe to copy onto one chemical.

    ``status`` is ``ok`` only for a single product substance. Mixture sheets,
    several candidate CAS numbers, a CAS that does not match the request, and
    unreadable text set ``share_sds`` so the UI can ask for the file.
    """
    label = filename.strip() or "uploaded SDS"
    requested = format_cas_display(requested_cas) if normalize_cas(requested_cas) else ""
    prepared = _prepare_text(text)
    if len(prepared.strip()) < 40:
        return _result(
            "unreadable",
            (
                f"Could not read text from {label}. It may be a scanned PDF. "
                f"{SHARE_SDS_MESSAGE}"
            ),
            share=True,
            filename=label,
        )

    hits = find_cas_hits(prepared)
    if not hits:
        return _result(
            "no_cas",
            (
                f"No CAS number with a valid check digit was found in {label}. "
                "SDS layouts differ, so this can be a reader miss. "
                f"{SHARE_SDS_MESSAGE}"
            ),
            share=True,
            filename=label,
        )

    all_cas = _unique(hits)
    product, mixture = _product_cas(hits)
    extra = [c for c in all_cas if c != product]

    if mixture or product is None:
        listed = _format_list(all_cas)
        lookup_hint = ""
        if not requested:
            lookup_hint = (
                " Enter one of those CAS numbers and click Generate to look that chemical up. "
            )
        return _result(
            "mixture" if mixture else "several_cas",
            (
                f"{label} lists more than one CAS ({listed}) and does not identify "
                "a single product substance. Nothing from the file was copied into "
                "the row, because mixture properties are not the properties of one ingredient. "
                f"{lookup_hint}{SHARE_SDS_MESSAGE}"
            ),
            share=True,
            filename=label,
            all_cas=all_cas,
        )

    if requested and normalize_cas(requested) != normalize_cas(product):
        return _result(
            "mismatch",
            (
                f"The CAS you entered ({requested}) is not the product CAS on {label} "
                f"({format_cas_display(product)}). The file was not used. "
                f"{SHARE_SDS_MESSAGE}"
            ),
            share=True,
            filename=label,
            product_cas=product,
            all_cas=all_cas,
        )

    fields = parse_sds_fields(prepared)
    extra_note = ""
    share = False
    if extra:
        extra_note = (
            f" Other CAS numbers on the sheet were not used: {_format_list(extra)}."
        )
        share = True
    message = (
        f"Used {label} for {format_cas_display(product)}. "
        "Only values the reader could match to a single product were filled, "
        f"and those cells are labelled uploaded SDS.{extra_note}"
    )
    if share:
        message = f"{message} {SHARE_SDS_MESSAGE}"
    return _result(
        "ok",
        message,
        share=share,
        filename=label,
        product_cas=product,
        all_cas=all_cas,
        fields=fields,
    )


def review_uploaded_sds(
    pdf_bytes: bytes,
    *,
    requested_cas: str = "",
    filename: str = "",
) -> dict[str, Any]:
    """Review an uploaded PDF. Non-PDF bytes are reported as unreadable."""
    return review_sds_text(
        pdf_bytes_to_text(pdf_bytes),
        requested_cas=requested_cas,
        filename=filename,
    )


def apply_uploaded_sds(row: dict[str, Any], review: dict[str, Any]) -> dict[str, Any]:
    """Write parsed SDS values onto the row when the review status is ``ok``. Never invents values."""
    row["_sds_upload"] = {
        "status": review.get("status"),
        "message": review.get("message"),
        "share_sds": bool(review.get("share_sds")),
        "product_cas": review.get("product_cas"),
        "all_cas": list(review.get("all_cas") or []),
    }
    notes = list(row.get("_enrich_notes") or [])
    notes.append(f"Uploaded SDS: {review.get('message')}")
    row["_enrich_notes"] = notes
    if review.get("status") != "ok":
        return row

    fields = review.get("fields") or {}
    sources = dict(row.get("_prop_sources") or {})
    src = "uploaded SDS"

    for key, col, digits in (
        ("boiling_point_c", "Boiling Point (C)", 1),
        ("melting_point_c", "Melting Point (C)", 1),
        ("flash_point_c", "Flash Point (C)", 1),
        ("density_g_l", "Density (g/L)", 1),
        ("vapor_pressure_mmhg", "Vapor Pressure (mmHg)", 2),
        ("viscosity_cp", "Viscosity (cP)", 3),
    ):
        if fields.get(key) is None:
            continue
        row[col] = str(round(float(fields[key]), digits))
        sources[col] = src

    raw_sol = fields.get("water_solubility_raw")
    if raw_sol:
        low = str(raw_sol).lower()
        if "miscible" in low:
            row["Water Solubility (g/L)"] = "miscible"
            sources["Water Solubility (g/L)"] = src
        elif "insoluble" in low or "immiscible" in low:
            row["Water Solubility (g/L)"] = "insoluble"
            sources["Water Solubility (g/L)"] = src

    for key, col in (("nfpa_health", "NFPA Health"), ("nfpa_flame", "NFPA Flame")):
        if not fields.get(key):
            continue
        row[col] = str(fields[key])
        sources[col] = src

    glove = (fields.get("glove_type") or "").strip()
    current = str(row.get("Glove Type") or "").strip()
    if glove and glove.lower() not in _GENERIC_GLOVE and current.lower() in _GENERIC_GLOVE:
        row["Glove Type"] = glove
        sources["Glove Type"] = src

    row["SDS Link"] = f"Uploaded file: {review.get('filename') or 'SDS'}"
    sources["SDS Link"] = src

    row["_prop_sources"] = sources
    return row


def _product_cas(hits: list[dict[str, Any]]) -> tuple[Optional[str], bool]:
    """Return (product CAS, is_mixture).

    A mixture is a composition section with more than one substance and no
    component at 90% or more. Those sheets are not applied.
    """
    composition = [h for h in hits if h["section"] == 3]
    identity = [h for h in hits if h["section"] == 1]
    major = [h for h in composition if h["percent"] is not None and h["percent"] >= 90]
    major_cas = _unique(major)

    if len(major_cas) > 1:
        return None, True
    if len(major_cas) == 1:
        return major_cas[0], False

    comp_cas = _unique(composition)
    if len(comp_cas) > 1:
        return None, True

    id_cas = _unique(identity)
    if len(comp_cas) == 1 and len(id_cas) <= 1:
        if id_cas and id_cas[0] != comp_cas[0]:
            return None, False
        return comp_cas[0], False
    if len(id_cas) == 1 and len(comp_cas) == 0:
        return id_cas[0], False
    if len(id_cas) > 1:
        return None, False

    everywhere = _unique(hits)
    if len(everywhere) == 1:
        return everywhere[0], False
    return None, False


def _result(
    status: str,
    message: str,
    *,
    share: bool,
    filename: str,
    product_cas: Optional[str] = None,
    all_cas: Optional[list[str]] = None,
    fields: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "message": message,
        "share_sds": share,
        "filename": filename,
        "product_cas": product_cas,
        "all_cas": list(all_cas or []),
        "fields": fields or {},
    }
