"""
CompTox DSSTox and ToxValDB adapters for auto_p2oasys.

Provides access to EPA CompTox Dashboard data:
- DSSTox: chemical identifiers, structure data
- ToxValDB: toxicity values from various sources
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..evidence import Evidence
from ..cas_utils import normalize_cas, format_cas_display


def _get_dsstox_cache_path() -> Path | None:
    """Find DSSTox cache parquet/sqlite."""
    env_path = os.environ.get("DSSTOX_CACHE_PATH", "").strip()
    if env_path and Path(env_path).is_file():
        return Path(env_path)

    candidates = [
        Path(__file__).resolve().parents[3] / "data" / "dsstox_cache.parquet",
        Path(__file__).resolve().parents[3] / "data" / "dsstox_cache.sqlite",
    ]
    for path in candidates:
        if path.is_file():
            return path

    return None


def is_dsstox_available() -> bool:
    """Check if DSSTox cache is available."""
    return _get_dsstox_cache_path() is not None


def gather_dsstox(cas: str) -> list[Evidence]:
    """
    Gather identity data from DSSTox cache.

    Returns DTXSID, SMILES, InChI, molecular formula if available.
    """
    cache_path = _get_dsstox_cache_path()
    if cache_path is None:
        return []

    evidence: list[Evidence] = []
    display_cas = format_cas_display(cas)
    digits = normalize_cas(cas)
    now = datetime.now(timezone.utc)

    try:
        if str(cache_path).endswith(".parquet"):
            import pandas as pd

            df = pd.read_parquet(cache_path)
            row = df[df["cas"].str.replace("-", "") == digits]
            if row.empty:
                return []
            row = row.iloc[0]
        else:
            conn = sqlite3.connect(str(cache_path))
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """SELECT * FROM dsstox
                   WHERE cas = ? OR REPLACE(cas, '-', '') = ?
                   LIMIT 1""",
                (display_cas, digits),
            ).fetchone()
            conn.close()
            if row is None:
                return []

        dtxsid = row.get("dtxsid") or row.get("DTXSID")
        if dtxsid:
            evidence.append(
                Evidence(
                    cas=display_cas,
                    endpoint="dtxsid",
                    value=dtxsid,
                    source="CompTox DSSTox",
                    predicted=False,
                    reference="EPA CompTox Chemicals Dashboard",
                    retrieved_at=now,
                )
            )

        smiles = row.get("smiles") or row.get("SMILES")
        if smiles:
            evidence.append(
                Evidence(
                    cas=display_cas,
                    endpoint="smiles",
                    value=smiles,
                    source="CompTox DSSTox",
                    predicted=False,
                    retrieved_at=now,
                )
            )

    except Exception:
        pass

    return evidence


def _get_toxvaldb_api_key() -> str | None:
    """Get EPA API key for ToxValDB."""
    return os.environ.get("EPA_API_KEY", "").strip() or None


def is_toxvaldb_available() -> bool:
    """Check if ToxValDB API is available."""
    return _get_toxvaldb_api_key() is not None


def gather_toxvaldb(cas: str) -> list[Evidence]:
    """
    Gather toxicity values from ToxValDB API.

    Returns oral LD50, dermal LD50, inhalation LC50, aquatic LC50 if available.
    Requires EPA_API_KEY environment variable.
    """
    api_key = _get_toxvaldb_api_key()
    if api_key is None:
        return []

    evidence: list[Evidence] = []
    display_cas = format_cas_display(cas)
    now = datetime.now(timezone.utc)

    try:
        import requests

        url = f"https://comptox.epa.gov/dashboard/api/toxval/{display_cas}"
        headers = {"x-api-key": api_key}
        resp = requests.get(url, headers=headers, timeout=30)

        if not resp.ok:
            return []

        data = resp.json()

        for record in data.get("records", []):
            endpoint = record.get("toxval_type", "").lower()
            value = record.get("toxval_numeric")
            unit = record.get("toxval_units")

            if value is None:
                continue

            evidence.append(
                Evidence(
                    cas=display_cas,
                    endpoint=endpoint,
                    value=value,
                    unit=unit,
                    source="ToxValDB",
                    predicted=False,
                    reliability=record.get("quality"),
                    reference=record.get("source"),
                    retrieved_at=now,
                )
            )

    except ImportError:
        pass
    except Exception:
        pass

    return evidence
