"""
CAMEO Chemicals NFPA 704 adapter for auto_p2oasys.

Looks up NFPA health and flammability ratings from the bundled CAMEO sqlite.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..evidence import Evidence
from ..cas_utils import normalize_cas, format_cas_display


def _get_cameo_db_path() -> Path | None:
    """Find CAMEO NFPA sqlite database."""
    env_path = os.environ.get("CAMEO_NFPA_DB", "").strip()
    if env_path and Path(env_path).is_file():
        return Path(env_path)

    try:
        from packages.p2oasys_scorer import config

        if hasattr(config, "CAMEO_NFPA_DB_PATH"):
            cfg_path = Path(config.CAMEO_NFPA_DB_PATH)
            if cfg_path.is_file():
                return cfg_path
    except ImportError:
        pass

    candidates = [
        Path(__file__).resolve().parents[2] / "p2oasys_scorer" / "data" / "cameo_nfpa.sqlite",
        Path(__file__).resolve().parents[3] / "data" / "cameo_nfpa.sqlite",
    ]
    for path in candidates:
        if path.is_file():
            return path

    return None


def gather_nfpa(cas: str) -> list[Evidence]:
    """
    Look up NFPA 704 ratings from CAMEO Chemicals database.

    Returns health and flammability ratings if found.
    """
    evidence: list[Evidence] = []
    display_cas = format_cas_display(cas)
    digits = normalize_cas(cas)
    now = datetime.now(timezone.utc)

    db_path = _get_cameo_db_path()
    if db_path is None:
        return []

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        row = conn.execute(
            """SELECT nfpa_health, nfpa_fire, nfpa_reactivity, nfpa_special
               FROM cameo_nfpa
               WHERE cas = ? OR REPLACE(cas, '-', '') = ?
               LIMIT 1""",
            (display_cas, digits),
        ).fetchone()

        conn.close()

        if row is None:
            return []

        health = row["nfpa_health"]
        if health is not None:
            evidence.append(
                Evidence(
                    cas=display_cas,
                    endpoint="nfpa_health",
                    value=int(health),
                    source="CAMEO",
                    predicted=False,
                    reference="CAMEO Chemicals NFPA 704",
                    retrieved_at=now,
                )
            )

        fire = row["nfpa_fire"]
        if fire is not None:
            evidence.append(
                Evidence(
                    cas=display_cas,
                    endpoint="nfpa_fire",
                    value=int(fire),
                    source="CAMEO",
                    predicted=False,
                    reference="CAMEO Chemicals NFPA 704",
                    retrieved_at=now,
                )
            )

    except Exception:
        pass

    return evidence
