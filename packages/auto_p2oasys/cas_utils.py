"""
CAS number utilities for auto_p2oasys.

Provides normalization, validation, and formatting of CAS registry numbers.
"""

from __future__ import annotations

import re
from typing import Optional


def normalize_cas(cas: str | None) -> str:
    """
    Normalize a CAS number to digits only.

    Args:
        cas: CAS number in any format (with or without hyphens)

    Returns:
        String of digits only, or empty string if invalid input
    """
    if not cas:
        return ""
    return "".join(c for c in str(cas) if c.isdigit())


def format_cas_display(cas: str | None) -> str:
    """
    Format a CAS number for display with standard hyphenation.

    Args:
        cas: CAS number (digits only or hyphenated)

    Returns:
        Hyphenated CAS number (e.g., "67-64-1") or original if too short
    """
    digits = normalize_cas(cas)
    if not digits:
        return (cas or "").strip()
    if len(digits) >= 5:
        return f"{digits[:-3]}-{digits[-3:-1]}-{digits[-1]}"
    return digits


def validate_cas_checksum(cas: str | None) -> bool:
    """
    Validate CAS number check digit (Luhn-like algorithm).

    The check digit is the last digit of the CAS number. It's computed as:
    sum(digit * position from right) mod 10 == check digit

    Args:
        cas: CAS number (with or without hyphens)

    Returns:
        True if check digit is valid, False otherwise
    """
    digits = normalize_cas(cas)
    if len(digits) < 5:
        return False

    check_digit = int(digits[-1])
    body = digits[:-1]

    total = 0
    for i, char in enumerate(reversed(body)):
        total += int(char) * (i + 1)

    return (total % 10) == check_digit


def extract_cas_from_text(text: str) -> list[str]:
    """
    Extract CAS numbers from text using regex.

    Finds patterns like 67-64-1, 7732-18-5, etc. and validates check digits.

    Args:
        text: Text to search for CAS numbers

    Returns:
        List of valid CAS numbers found (hyphenated format)
    """
    if not text:
        return []

    pattern = r"\b(\d{2,7})-(\d{2})-(\d)\b"
    matches = re.findall(pattern, text)

    valid_cas = []
    for match in matches:
        cas = f"{match[0]}-{match[1]}-{match[2]}"
        if validate_cas_checksum(cas):
            valid_cas.append(cas)

    return valid_cas


def cas_to_key(cas: str | None) -> str:
    """
    Convert CAS to lookup key (digits only, zero-padded if needed).

    Args:
        cas: CAS number in any format

    Returns:
        Normalized key for database lookups
    """
    digits = normalize_cas(cas)
    return digits if digits else ""
