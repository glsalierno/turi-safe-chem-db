"""
CAMEO Chemicals NFPA 704 adapter for auto_p2oasys.

Looks up NFPA health, flammability, and reactivity ratings from the bundled CAMEO sqlite.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ..evidence import Evidence
from ..cas_utils import normalize_cas, format_cas_display


class CameoError(Exception):
    """Error accessing CAMEO database."""
    pass


def _get_cameo_db_path() -> Path | None:
    """Find CAMEO NFPA sqlite database via capability_config."""
    try:
        from packages.capability_config import ScorerConfig
        cfg_path = ScorerConfig.cameo_nfpa_db()
        if cfg_path and cfg_path.is_file():
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


def is_cameo_available() -> bool:
    """Check if CAMEO database is available."""
    return _get_cameo_db_path() is not None


def gather_nfpa(cas: str) -> list[Evidence]:
    """
    Look up NFPA 704 ratings from CAMEO Chemicals database.

    Returns health, flammability, and reactivity ratings if found.
    Real column names: nfpa_health, nfpa_flam, nfpa_react, nfpa_special.

    Raises:
        CameoError: If database access fails (not silently swallowed).
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
            """SELECT nfpa_health, nfpa_flam, nfpa_react, nfpa_special
               FROM cameo_nfpa
               WHERE cas = ? OR cas_nodash = ?
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

        flam = row["nfpa_flam"]
        if flam is not None:
            evidence.append(
                Evidence(
                    cas=display_cas,
                    endpoint="nfpa_flam",
                    value=int(flam),
                    source="CAMEO",
                    predicted=False,
                    reference="CAMEO Chemicals NFPA 704",
                    retrieved_at=now,
                )
            )

        react = row["nfpa_react"]
        if react is not None:
            evidence.append(
                Evidence(
                    cas=display_cas,
                    endpoint="nfpa_react",
                    value=int(react),
                    source="CAMEO",
                    predicted=False,
                    reference="CAMEO Chemicals NFPA 704",
                    retrieved_at=now,
                )
            )

        special = row["nfpa_special"]
        if special is not None:
            evidence.append(
                Evidence(
                    cas=display_cas,
                    endpoint="nfpa_special",
                    value=str(special),
                    source="CAMEO",
                    predicted=False,
                    reference="CAMEO Chemicals NFPA 704",
                    retrieved_at=now,
                )
            )

    except sqlite3.Error as e:
        raise CameoError(f"CAMEO database error: {e}") from e

    return evidence
