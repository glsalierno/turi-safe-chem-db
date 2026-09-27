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
    """Load CSV file and index by normalized CAS."""
    data_dir = _get_data_dir()
    path = data_dir / filename

    if not path.is_file():
        return {}

    result = {}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                cas = normalize_cas(row.get(cas_col, ""))
                if cas:
                    result[cas] = row
    except Exception:
        pass

    return result


_IARC_CACHE: dict[str, dict] | None = None
_ODP_GWP_CACHE: dict[str, dict] | None = None
_HAP_CACHE: dict[str, dict] | None = None


def gather_iarc(cas: str) -> list[Evidence]:
    """
    Look up IARC carcinogenicity classification.

    Returns IARC group (1, 2A, 2B, 3) if found.
    """
    global _IARC_CACHE

    if _IARC_CACHE is None:
        _IARC_CACHE = _load_csv_by_cas("iarc_by_cas.csv")

    digits = normalize_cas(cas)
    display_cas = format_cas_display(cas)
    now = datetime.now(timezone.utc)

    row = _IARC_CACHE.get(digits)
    if row is None:
        return []

    iarc_group = row.get("iarc_group") or row.get("group") or row.get("classification")
    if not iarc_group:
        return []

    return [
        Evidence(
            cas=display_cas,
            endpoint="iarc",
            value=iarc_group.strip(),
            source="IARC",
            predicted=False,
            reference="IARC Monographs",
            retrieved_at=now,
        )
    ]


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
