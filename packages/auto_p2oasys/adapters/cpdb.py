"""
CPDB (Carcinogenic Potency Database) adapter for auto_p2oasys.

Provides TD50 values for carcinogenicity assessment.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..evidence import Evidence
from ..cas_utils import normalize_cas, format_cas_display


class CPDBError(Exception):
    """Error accessing CPDB database."""
    pass


def _row_get(row: Any, key: str, default: Any = None) -> Any:
    """Get value from sqlite3.Row safely."""
    try:
        val = row[key]
        return val if val is not None else default
    except (KeyError, IndexError, TypeError):
        return default


def _get_cpdb_path() -> Path | None:
    """Find CPDB sqlite database via capability_config."""
    try:
        from packages.capability_config import ExternalToolsConfig
        cfg_path = ExternalToolsConfig.cpdb_db_path()
        if cfg_path and cfg_path.is_file():
            return cfg_path
    except ImportError:
        pass

    candidates = [
        Path(__file__).resolve().parents[3] / "data" / "carcinogenic_potency.sqlite",
        Path(__file__).resolve().parents[3] / "data" / "cpdb.sqlite",
    ]
    for path in candidates:
        if path.is_file():
            return path

    return None


def is_cpdb_available() -> bool:
    """Check if CPDB database is available."""
    return _get_cpdb_path() is not None


def gather_cpdb(cas: str) -> list[Evidence]:
    """
    Gather TD50 carcinogenic potency from CPDB.

    Returns TD50 values for different species/routes if available.
    
    Raises:
        CPDBError: If database access fails (not silently swallowed).
    """
    db_path = _get_cpdb_path()
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
            """SELECT * FROM cpdb
               WHERE cas = ? OR REPLACE(cas, '-', '') = ?""",
            (display_cas, digits),
        ).fetchall()

        conn.close()

        for row in rows:
            td50 = _row_get(row, "td50") or _row_get(row, "TD50")
            if td50 is None:
                continue

            species = _row_get(row, "species", "")
            route = _row_get(row, "route", "")
            target = _row_get(row, "target_organ", "")
            qualifier = _row_get(row, "qualifier")

            evidence.append(
                Evidence(
                    cas=display_cas,
                    endpoint="td50",
                    value=float(td50),
                    unit="mg/kg/day",
                    qualifier=qualifier,
                    source="CPDB",
                    predicted=False,
                    reference=f"CPDB {species} {route} {target}".strip(),
                    retrieved_at=now,
                )
            )

    except sqlite3.Error as e:
        raise CPDBError(f"CPDB database error: {e}") from e

    return evidence
