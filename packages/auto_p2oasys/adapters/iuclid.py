"""
IUCLID adapter for auto_p2oasys.

Provides access to ECHA REACH study results from IUCLID dossiers.

CRITICAL ATTRIBUTION REQUIREMENT:
Any result derived from IUCLID data MUST display:
    Source: ECHA REACH Study Results (IUCLID), European Chemicals Agency

This is a legal/attribution requirement, not optional.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..evidence import Evidence
from ..cas_utils import normalize_cas, format_cas_display


ECHA_ATTRIBUTION = "ECHA REACH Study Results (IUCLID), European Chemicals Agency"

IUCLID_ENDPOINTS = {
    "inhalation_lc50": {
        "section": "7.2.2",
        "description": "Acute toxicity: inhalation",
        "unit": "mg/L",
    },
    "repeated_dose_toxicity": {
        "section": "7.5",
        "description": "Repeated dose toxicity",
        "unit": "mg/kg/day",
    },
    "genotoxicity_in_vitro": {
        "section": "7.6.1",
        "description": "Genetic toxicity in vitro",
        "unit": None,
    },
    "genotoxicity_in_vivo": {
        "section": "7.6.2",
        "description": "Genetic toxicity in vivo",
        "unit": None,
    },
    "biodegradation": {
        "section": "9.2.1",
        "description": "Biodegradation in water: screening tests",
        "unit": "%",
    },
    "chronic_aquatic_noec": {
        "section": "9.1.6",
        "description": "Long-term toxicity to aquatic invertebrates",
        "unit": "mg/L",
    },
}


def _get_iuclid_cache_path() -> Path | None:
    """Find IUCLID cache sqlite database."""
    env_path = os.environ.get("IUCLID_CACHE_DB", "").strip()
    if env_path and Path(env_path).is_file():
        return Path(env_path)

    try:
        from packages.p2oasys_scorer import config

        if hasattr(config, "IUCLID_CACHE_DB"):
            cfg_path = Path(config.IUCLID_CACHE_DB)
            if cfg_path.is_file():
                return cfg_path
    except ImportError:
        pass

    candidates = [
        Path(__file__).resolve().parents[3] / "data" / "iuclid_cache.sqlite",
        Path(__file__).resolve().parents[2] / "p2oasys_scorer" / "data" / "iuclid_cache.sqlite",
    ]
    for path in candidates:
        if path.is_file():
            return path

    return None


def gather_iuclid(cas: str) -> list[Evidence]:
    """
    Gather endpoints from IUCLID dossier cache.

    Returns evidence for:
    - Inhalation LC50
    - Repeated dose toxicity
    - Genotoxicity (in vitro and in vivo)
    - Biodegradation
    - Chronic aquatic NOEC

    All IUCLID-sourced evidence carries ECHA attribution.
    """
    db_path = _get_iuclid_cache_path()
    if db_path is None:
        return []

    evidence: list[Evidence] = []
    display_cas = format_cas_display(cas)
    digits = normalize_cas(cas)
    now = datetime.now(timezone.utc)

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        rows = conn.execute(
            """SELECT endpoint_type, value, unit, qualifier, reliability, 
                      study_type, guideline, reference_year
               FROM iuclid_endpoints
               WHERE cas = ? OR REPLACE(cas, '-', '') = ?""",
            (display_cas, digits),
        ).fetchall()

        conn.close()

        for row in rows:
            endpoint_type = row["endpoint_type"]
            value = row["value"]

            if value is None:
                continue

            endpoint_info = IUCLID_ENDPOINTS.get(endpoint_type, {})

            ev = Evidence(
                cas=display_cas,
                endpoint=endpoint_type,
                value=value,
                unit=row["unit"] or endpoint_info.get("unit"),
                qualifier=row["qualifier"],
                source=ECHA_ATTRIBUTION,
                predicted=False,
                reliability=row["reliability"],
                reference=_format_iuclid_reference(row),
                section=endpoint_info.get("section"),
                retrieved_at=now,
            )
            evidence.append(ev)

    except Exception:
        pass

    return evidence


def gather_inhalation_lc50(cas: str) -> list[Evidence]:
    """Gather inhalation LC50 from IUCLID."""
    all_evidence = gather_iuclid(cas)
    return [e for e in all_evidence if e.endpoint == "inhalation_lc50"]


def gather_repeated_dose(cas: str) -> list[Evidence]:
    """Gather repeated dose toxicity from IUCLID."""
    all_evidence = gather_iuclid(cas)
    return [e for e in all_evidence if e.endpoint == "repeated_dose_toxicity"]


def gather_genotoxicity(cas: str) -> list[Evidence]:
    """Gather genotoxicity data from IUCLID."""
    all_evidence = gather_iuclid(cas)
    return [e for e in all_evidence if "genotoxicity" in e.endpoint]


def gather_biodegradation(cas: str) -> list[Evidence]:
    """Gather biodegradation data from IUCLID."""
    all_evidence = gather_iuclid(cas)
    return [e for e in all_evidence if e.endpoint == "biodegradation"]


def gather_chronic_aquatic(cas: str) -> list[Evidence]:
    """Gather chronic aquatic NOEC from IUCLID."""
    all_evidence = gather_iuclid(cas)
    return [e for e in all_evidence if e.endpoint == "chronic_aquatic_noec"]


def _format_iuclid_reference(row) -> str:
    """Format IUCLID study reference."""
    parts = [ECHA_ATTRIBUTION]

    guideline = row.get("guideline")
    if guideline:
        parts.append(f"Guideline: {guideline}")

    study_type = row.get("study_type")
    if study_type:
        parts.append(f"Study: {study_type}")

    year = row.get("reference_year")
    if year:
        parts.append(f"Year: {year}")

    return " | ".join(parts)


def is_iuclid_available() -> bool:
    """Check if IUCLID cache is available."""
    return _get_iuclid_cache_path() is not None
