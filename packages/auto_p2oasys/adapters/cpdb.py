"""
CPDB (Carcinogenic Potency Database) adapter for auto_p2oasys.

Provides TD50 values for carcinogenicity assessment.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..evidence import Evidence
from ..cas_utils import normalize_cas, format_cas_display


def _get_cpdb_path() -> Path | None:
    """Find CPDB sqlite database."""
    env_path = os.environ.get("CPDB_DB_PATH", "").strip()
    if env_path and Path(env_path).is_file():
        return Path(env_path)

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
            td50 = row.get("td50") or row.get("TD50")
            if td50 is None:
                continue

            species = row.get("species", "")
            route = row.get("route", "")
            target = row.get("target_organ", "")

            evidence.append(
                Evidence(
                    cas=display_cas,
                    endpoint="td50",
                    value=float(td50),
                    unit="mg/kg/day",
                    qualifier=row.get("qualifier"),
                    source="CPDB",
                    predicted=False,
                    reference=f"CPDB {species} {route} {target}".strip(),
                    retrieved_at=now,
                )
            )

    except Exception:
        pass

    return evidence
