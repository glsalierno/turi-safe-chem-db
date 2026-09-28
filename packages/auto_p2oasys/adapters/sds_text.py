"""
SDS PDF text extraction - ported from GHaz7 sds_pdf_utils.py (Gabriel Salierno), offline subset.

Extracts text from SDS PDFs using pdfplumber (optional) or pypdf.
NO OCR support in this offline version.
"""
from __future__ import annotations

import re
import warnings
from pathlib import Path
from typing import Optional

# Section patterns for SDS parsing - ported from GHaz7 sds_regex_extractor.py
SECTION_PATTERNS = {
    1: re.compile(r"(?i)(?:section\s*)?1[:\.\s]+(?:identification|product\s+identifier)", re.IGNORECASE),
    2: re.compile(r"(?i)(?:section\s*)?2[:\.\s]+(?:hazards?\s+identification|classification)", re.IGNORECASE),
    3: re.compile(r"(?i)(?:section\s*)?3[:\.\s]+(?:composition|ingredients?)", re.IGNORECASE),
    4: re.compile(r"(?i)(?:section\s*)?4[:\.\s]+(?:first\s+aid)", re.IGNORECASE),
    5: re.compile(r"(?i)(?:section\s*)?5[:\.\s]+(?:fire\s*[-\s]*fighting)", re.IGNORECASE),
    6: re.compile(r"(?i)(?:section\s*)?6[:\.\s]+(?:accidental\s+release)", re.IGNORECASE),
    7: re.compile(r"(?i)(?:section\s*)?7[:\.\s]+(?:handling\s+and\s+storage)", re.IGNORECASE),
    8: re.compile(r"(?i)(?:section\s*)?8[:\.\s]+(?:exposure\s+controls|personal\s+protection)", re.IGNORECASE),
    9: re.compile(r"(?i)(?:section\s*)?9[:\.\s]+(?:physical\s+and\s+chemical\s+properties)", re.IGNORECASE),
    10: re.compile(r"(?i)(?:section\s*)?10[:\.\s]+(?:stability\s+and\s+reactivity)", re.IGNORECASE),
    11: re.compile(r"(?i)(?:section\s*)?11[:\.\s]+(?:toxicological\s+information)", re.IGNORECASE),
    12: re.compile(r"(?i)(?:section\s*)?12[:\.\s]+(?:ecological\s+information)", re.IGNORECASE),
    13: re.compile(r"(?i)(?:section\s*)?13[:\.\s]+(?:disposal\s+considerations)", re.IGNORECASE),
    14: re.compile(r"(?i)(?:section\s*)?14[:\.\s]+(?:transport\s+information)", re.IGNORECASE),
    15: re.compile(r"(?i)(?:section\s*)?15[:\.\s]+(?:regulatory\s+information)", re.IGNORECASE),
    16: re.compile(r"(?i)(?:section\s*)?16[:\.\s]+(?:other\s+information)", re.IGNORECASE),
}

MIN_TEXT_LENGTH = 250


def extract_text_from_pdf(path: Path) -> tuple[str, str]:
    """
    Extract text from PDF using available libraries.
    
    Returns:
        (text, backend) where backend is "pdfplumber", "pypdf", or "error"
    """
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            text_parts = []
            for page in pdf.pages:
                text = page.extract_text() or ""
                text_parts.append(text)
            text = "\n".join(text_parts)
            return _normalize_text(text), "pdfplumber"
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
        text = "\n".join(text_parts)
        return _normalize_text(text), "pypdf"
    except ImportError:
        pass
    except Exception:
        pass
    
    warnings.warn(
        "No PDF text backend available (pip install pypdf)",
        RuntimeWarning,
    )
    return "", "error"


def extract_text_from_bytes(pdf_bytes: bytes) -> tuple[str, str]:
    """Extract text from PDF bytes."""
    from io import BytesIO
    
    try:
        import pdfplumber
        with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
            text_parts = []
            for page in pdf.pages:
                text = page.extract_text() or ""
                text_parts.append(text)
            text = "\n".join(text_parts)
            return _normalize_text(text), "pdfplumber"
    except ImportError:
        pass
    except Exception:
        pass
    
    try:
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(pdf_bytes))
        text_parts = []
        for page in reader.pages:
            text = page.extract_text() or ""
            text_parts.append(text)
        text = "\n".join(text_parts)
        return _normalize_text(text), "pypdf"
    except ImportError:
        pass
    except Exception:
        pass
    
    return "", "error"


def _normalize_text(text: str) -> str:
    """Normalize Unicode characters for consistent parsing."""
    if not text:
        return ""
    text = text.replace("\u2212", "-")
    text = text.replace("\u2013", "-")
    text = text.replace("\u2014", "-")
    text = text.replace("\u2010", "-")
    text = text.replace("\u2011", "-")
    text = text.replace("\u00b0", "°")
    return text


def split_sections(text: str) -> dict[int, str]:
    """
    Split SDS text into sections using anchored headers.
    
    Returns dict mapping section number (1-16) to section content.
    Uses SECTION_PATTERNS for robust matching.
    """
    if not text or len(text) < 50:
        return {}
    
    matches: list[tuple[int, int]] = []
    
    for num, pattern in SECTION_PATTERNS.items():
        for m in pattern.finditer(text):
            matches.append((num, m.start()))
    
    matches.sort(key=lambda x: x[1])
    
    if len(matches) < 3:
        return _fallback_section_split(text)
    
    sections: dict[int, str] = {}
    for i, (num, start) in enumerate(matches):
        if i + 1 < len(matches):
            end = matches[i + 1][1]
        else:
            end = len(text)
        
        header_end = text.find("\n", start)
        if header_end == -1 or header_end > start + 200:
            header_end = start + 50
        
        content = text[header_end:end].strip()
        if content:
            sections[num] = content[:8000]
    
    return sections


def _fallback_section_split(text: str) -> dict[int, str]:
    """
    Fallback section splitter for SDSs with non-standard headers.
    
    Splits on lines that start with a number 1-16 followed by text.
    NOTE: This can break on table rows like "2 mg/L", so only use as fallback.
    """
    sections: dict[int, str] = {}
    
    simple_pattern = re.compile(r"^\s*(\d{1,2})\s*[.:\s]+\s*\w", re.MULTILINE)
    
    matches = list(simple_pattern.finditer(text))
    valid_matches = []
    for m in matches:
        try:
            num = int(m.group(1))
            if 1 <= num <= 16:
                valid_matches.append((num, m.start()))
        except ValueError:
            pass
    
    if len(valid_matches) < 2:
        return sections
    
    valid_matches.sort(key=lambda x: x[1])
    
    for i, (num, start) in enumerate(valid_matches):
        if i + 1 < len(valid_matches):
            end = valid_matches[i + 1][1]
        else:
            end = len(text)
        
        content = text[start:end]
        header_end = content.find("\n")
        if header_end > 0:
            content = content[header_end:].strip()
        
        if content and num not in sections:
            sections[num] = content[:8000]
    
    return sections


def get_n_pages(path: Path) -> int:
    """Get page count from PDF."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(path)
        return len(reader.pages)
    except Exception:
        pass
    
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            return len(pdf.pages)
    except Exception:
        pass
    
    return 0


def is_scanned_pdf(text: str) -> bool:
    """Check if the PDF appears to be scanned (minimal text)."""
    return len(text.strip()) < MIN_TEXT_LENGTH
