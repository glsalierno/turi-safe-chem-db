"""
Automatic P2OASys scoring with expert-first routing and fast pipeline fallback.

Entry point for clean automatic hazard scoring. Expert scores from the bundled
SQLite are used when available; the fast pipeline computes scores from upstream
data sources when expert scores are missing or when forced.

Usage:
    from packages.auto_p2oasys import auto_p2oasys

    result = auto_p2oasys("67-64-1")  # Returns expert if available
    result = auto_p2oasys("67-64-1", force_fast=True)  # Also runs fast pipeline

CLI:
    python -m packages.auto_p2oasys --cas 67-64-1 [--fast] [--sds file.pdf] [--json out.json]
"""

from __future__ import annotations

__version__ = "0.1.0"

from .core import auto_p2oasys, P2OASysResult, P2OASysMode
from .evidence import Evidence
from .cas_utils import normalize_cas, validate_cas_checksum, format_cas_display
from .source_report import SourceReport, AdapterStatus

__all__ = [
    "__version__",
    "auto_p2oasys",
    "P2OASysResult",
    "P2OASysMode",
    "Evidence",
    "normalize_cas",
    "validate_cas_checksum",
    "format_cas_display",
    "SourceReport",
    "AdapterStatus",
]
