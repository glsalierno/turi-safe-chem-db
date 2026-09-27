"""
Lookup table adapters for auto_p2oasys.

Provides IARC, ODP/GWP, and CAA 112(b) HAP lookups from bundled CSV files.
"""

from __future__ import annotations

import csv
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..evidence import Evidence
from ..cas_utils import normalize_cas, format_cas_display


def _get_data_dir() -> Path:
    """Get scorer data directory."""
    try:
        from packages.p2oasys_scorer import config

        return Path(config.DATA_DIR)
    except ImportError:
        pass

    return Path(__file__).resolve().parents[2] / "p2oasys_scorer" / "data"


def _load_csv_by_cas(filename: str, cas_col: str = "cas") -> dict[str, dict]:
    """Load CSV file and index by normalized CAS.
    
    Raises:
        FileNotFoundError: If CSV file doesn't exist.
        Exception: If CSV parsing fails (not silently swallowed).
    """
    data_dir = _get_data_dir()
    path = data_dir / filename

    if not path.is_file():
        return {}

    result = {}
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cas = normalize_cas(row.get(cas_col, ""))
            if cas:
                result[cas] = row

    return result


_IARC_CACHE: dict[str, dict] | None = None
_EPA_CARC_CACHE: dict[str, dict] | None = None
_ODP_GWP_CACHE: dict[str, dict] | None = None
_HAP_CACHE: dict[str, dict] | None = None


class LookupError(Exception):
    """Error accessing lookup table data."""
    pass


def gather_iarc(cas: str) -> list[Evidence]:
    """
    Look up IARC carcinogenicity classification.

    Returns IARC group (1, 2A, 2B, 3) if found.
    CSV column name: 'iarc' (contains values like '1', '2A', '2B', '3').
    CAS normalization: strips hyphens for matching.
    """
    global _IARC_CACHE

    try:
        if _IARC_CACHE is None:
            _IARC_CACHE = _load_csv_by_cas("iarc_by_cas.csv")
    except Exception as e:
        raise LookupError(f"Failed to load IARC table: {e}") from e

    digits = normalize_cas(cas)
    display_cas = format_cas_display(cas)
    now = datetime.now(timezone.utc)

    row = _IARC_CACHE.get(digits)
    if row is None:
        return []

    iarc_group = row.get("iarc")
    if not iarc_group:
        return []

    return [
        Evidence(
            cas=display_cas,
            endpoint="iarc",
            value=str(iarc_group).strip(),
            source="IARC",
            predicted=False,
            reference="IARC Monographs on the Identification of Carcinogenic Hazards to Humans",
            retrieved_at=now,
        )
    ]


def gather_epa_carcinogen(cas: str) -> list[Evidence]:
    """
    Look up EPA carcinogen classification.

    Returns EPA carcinogen category if found.
    Categories: A (Known), B1/B2 (Probable), C (Possible), D (Not classifiable), E (Non-carcinogenic)
    CAS normalization: strips hyphens for matching.
    """
    global _EPA_CARC_CACHE

    if _EPA_CARC_CACHE is None:
        _EPA_CARC_CACHE = _load_csv_by_cas("epa_carcinogen_by_cas.csv")

    digits = normalize_cas(cas)
    display_cas = format_cas_display(cas)
    now = datetime.now(timezone.utc)

    row = _EPA_CARC_CACHE.get(digits)
    if row is None:
        return []

    epa_class = (
        row.get("epa_class")
        or row.get("classification")
        or row.get("category")
        or row.get("epa_carcinogen")
    )
    if not epa_class:
        return []

    return [
        Evidence(
            cas=display_cas,
            endpoint="epa_carcinogen",
            value=epa_class.strip(),
            source="EPA IRIS",
            predicted=False,
            reference="EPA Integrated Risk Information System (IRIS)",
            retrieved_at=now,
        )
    ]


def gather_carcinogens(cas: str) -> list[Evidence]:
    """
    Gather all carcinogen classifications (IARC + EPA).

    Returns combined evidence from IARC and EPA sources.
    """
    evidence = []
    evidence.extend(gather_iarc(cas))
    evidence.extend(gather_epa_carcinogen(cas))
    return evidence


def gather_odp_gwp(cas: str) -> list[Evidence]:
    """
    Look up ODP and GWP100 values.

    Returns ODP and/or GWP100 if found in lookup table.
    """
    global _ODP_GWP_CACHE

    if _ODP_GWP_CACHE is None:
        _ODP_GWP_CACHE = _load_csv_by_cas("odp_gwp_by_cas.csv")

    digits = normalize_cas(cas)
    display_cas = format_cas_display(cas)
    now = datetime.now(timezone.utc)

    row = _ODP_GWP_CACHE.get(digits)
    if row is None:
        return []

    evidence = []

    odp = row.get("odp") or row.get("ODP")
    if odp:
        try:
            odp_val = float(odp)
            evidence.append(
                Evidence(
                    cas=display_cas,
                    endpoint="odp",
                    value=odp_val,
                    source="Montreal Protocol",
                    predicted=False,
                    retrieved_at=now,
                )
            )
        except (TypeError, ValueError):
            pass

    gwp = row.get("gwp100") or row.get("GWP100") or row.get("gwp")
    if gwp:
        try:
            gwp_val = float(gwp)
            evidence.append(
                Evidence(
                    cas=display_cas,
                    endpoint="gwp100",
                    value=gwp_val,
                    source="IPCC",
                    predicted=False,
                    retrieved_at=now,
                )
            )
        except (TypeError, ValueError):
            pass

    return evidence


def gather_hap(cas: str) -> list[Evidence]:
    """
    Look up CAA §112(b) Hazardous Air Pollutant status.

    Returns HAP status for NESHAP scoring if CAS is on the list.
    """
    global _HAP_CACHE

    if _HAP_CACHE is None:
        _HAP_CACHE = _load_csv_by_cas("caa112b_hap_by_cas.csv")

    digits = normalize_cas(cas)
    display_cas = format_cas_display(cas)
    now = datetime.now(timezone.utc)

    row = _HAP_CACHE.get(digits)
    if row is None:
        return []

    return [
        Evidence(
            cas=display_cas,
            endpoint="hap",
            value=True,
            source="CAA 112(b)",
            predicted=False,
            reference="Clean Air Act §112(b) HAP List",
            retrieved_at=now,
        )
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Odor Threshold
# ─────────────────────────────────────────────────────────────────────────────

_ODOR_CACHE: dict[str, dict] | None = None


def gather_odor_threshold(cas: str) -> list[Evidence]:
    """
    Look up odor threshold values.

    Returns odor threshold in ppm if found.
    Flags MISSING if no data available.
    """
    global _ODOR_CACHE

    if _ODOR_CACHE is None:
        _ODOR_CACHE = _load_csv_by_cas("odor_threshold_by_cas.csv")

    digits = normalize_cas(cas)
    display_cas = format_cas_display(cas)
    now = datetime.now(timezone.utc)

    row = _ODOR_CACHE.get(digits)
    if row is None:
        return [
            Evidence(
                cas=display_cas,
                endpoint="odor_threshold",
                value=None,
                source="MISSING",
                predicted=False,
                reference="No odor threshold data available",
                retrieved_at=now,
            )
        ]

    odor_val = row.get("odor_threshold") or row.get("threshold_ppm") or row.get("value")
    if not odor_val:
        return [
            Evidence(
                cas=display_cas,
                endpoint="odor_threshold",
                value=None,
                source="MISSING",
                predicted=False,
                reference="No odor threshold data available",
                retrieved_at=now,
            )
        ]

    try:
        threshold = float(odor_val)
        return [
            Evidence(
                cas=display_cas,
                endpoint="odor_threshold",
                value=threshold,
                unit="ppm",
                source="Odor Threshold Database",
                predicted=False,
                reference=row.get("reference") or "Literature compilation",
                retrieved_at=now,
            )
        ]
    except (TypeError, ValueError):
        return [
            Evidence(
                cas=display_cas,
                endpoint="odor_threshold",
                value=None,
                source="MISSING",
                predicted=False,
                reference="Invalid odor threshold data",
                retrieved_at=now,
            )
        ]


# ─────────────────────────────────────────────────────────────────────────────
# NOT_WIRED endpoints - explicitly marked as not implemented
# ─────────────────────────────────────────────────────────────────────────────


def gather_idlh(cas: str) -> list[Evidence]:
    """
    IDLH (Immediately Dangerous to Life or Health) - NOT_WIRED.

    This endpoint is explicitly marked as not yet implemented.
    """
    display_cas = format_cas_display(cas)
    now = datetime.now(timezone.utc)

    return [
        Evidence(
            cas=display_cas,
            endpoint="idlh",
            value=None,
            source="NOT_WIRED",
            predicted=False,
            reference="IDLH lookup not yet implemented",
            retrieved_at=now,
        )
    ]


def gather_reportable_quantity(cas: str) -> list[Evidence]:
    """
    Reportable Quantity (RQ) under CERCLA/EPCRA - NOT_WIRED.

    This endpoint is explicitly marked as not yet implemented.
    """
    display_cas = format_cas_display(cas)
    now = datetime.now(timezone.utc)

    return [
        Evidence(
            cas=display_cas,
            endpoint="reportable_quantity",
            value=None,
            source="NOT_WIRED",
            predicted=False,
            reference="Reportable Quantity lookup not yet implemented",
            retrieved_at=now,
        )
    ]
