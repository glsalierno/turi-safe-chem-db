"""
P2OASys automatic hazard assessment spine.

Provides a unified assess() entry point for automatic hazard scoring.
Returns Auto6 category scores only — Process Factors and Life Cycle Factors
are intentionally omitted (human expert input required).

Auto6 Categories:
  - Acute Human Effects
  - Chronic Human Effects
  - Ecological Hazards
  - Environmental Fate & Transport
  - Atmospheric Hazard
  - Physical Properties

Overall = max of Auto6 category maxes (existing convention).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from packages.p2oasys_core.lookup import (
    SQLITE_AUTO_AUTO6,
    SQLITE_EXPERT_AUTO6,
    _to_float,
    default_lookup_db_path,
    format_cas_display,
    max_of_values,
    normalize_cas,
)


@dataclass(frozen=True)
class AssessmentResult:
    """
    Result of P2OASys automatic hazard assessment.

    Contains Auto6 category scores only. Process Factors and Life Cycle
    Factors are intentionally excluded (human expert input required).

    Attributes:
        cas: Normalized CAS number (formatted with dashes).
        acute: Acute Human Effects max score (1-10 or None).
        chronic: Chronic Human Effects max score (1-10 or None).
        ecological: Ecological Hazards max score (1-10 or None).
        fate: Environmental Fate & Transport max score (1-10 or None).
        atmospheric: Atmospheric Hazard max score (1-10 or None).
        physical: Physical Properties max score (1-10 or None).
        overall: Max of Auto6 category scores (1-10 or None).
        source: Data source — 'expert', 'auto', or 'not_found'.
        name: Chemical name if available.
    """

    cas: str
    acute: Optional[float]
    chronic: Optional[float]
    ecological: Optional[float]
    fate: Optional[float]
    atmospheric: Optional[float]
    physical: Optional[float]
    overall: Optional[float]
    source: str
    name: Optional[str] = None


def _fetch_sqlite_row(cas: str, db_path: Path | str | None = None) -> Optional[dict[str, Any]]:
    """Fetch raw row from SQLite by_cas table."""
    path = Path(db_path) if db_path else default_lookup_db_path()
    if not path.is_file():
        return None
    key = normalize_cas(cas)
    if not key:
        return None
    disp = format_cas_display(key)
    try:
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT * FROM by_cas WHERE cas = ? OR REPLACE(cas, '-', '') = ? LIMIT 1",
                (disp, key),
            ).fetchone()
            if row is None:
                return None
            return {k: row[k] for k in row.keys()}
        finally:
            conn.close()
    except Exception:
        return None


def _extract_auto6_scores(
    row: dict[str, Any],
    columns: tuple[str, ...],
) -> dict[str, Optional[float]]:
    """Extract Auto6 category scores from a SQLite row."""
    mapping = {
        "acute": columns[0],
        "chronic": columns[1],
        "ecological": columns[2],
        "fate": columns[3],
        "atmospheric": columns[4],
        "physical": columns[5],
    }
    return {key: _to_float(row.get(col)) for key, col in mapping.items()}


def assess(
    cas: str,
    sds_data: Optional[dict[str, Any]] = None,
    *,
    db_path: Path | str | None = None,
) -> AssessmentResult:
    """
    Assess hazard scores for a chemical by CAS.

    Returns Auto6 category scores only. Process Factors and Life Cycle
    Factors are intentionally omitted (human expert input required).

    Lookup priority:
      1. SQLite expert scores (has_expert=1)
      2. SQLite auto scores (has_auto=1)
      3. Not found (all scores None, source='not_found')

    Args:
        cas: CAS number (any format — dashes optional, whitespace ignored).
        sds_data: Optional SDS data dict (reserved for future enrichment).
        db_path: Optional override for the score lookup SQLite path.

    Returns:
        AssessmentResult with Auto6 category scores and overall max.
        Never invents scores — missing categories return None.
    """
    key = normalize_cas(cas)
    cas_display = format_cas_display(key) if key else (cas or "").strip()

    row = _fetch_sqlite_row(cas, db_path)
    if row is None:
        return AssessmentResult(
            cas=cas_display,
            acute=None,
            chronic=None,
            ecological=None,
            fate=None,
            atmospheric=None,
            physical=None,
            overall=None,
            source="not_found",
            name=None,
        )

    source: str
    scores: dict[str, Optional[float]]
    name: Optional[str]

    if row.get("has_expert"):
        source = "expert"
        scores = _extract_auto6_scores(row, SQLITE_EXPERT_AUTO6)
        name = row.get("name_expert") or row.get("name_auto")
    elif row.get("has_auto"):
        source = "auto"
        scores = _extract_auto6_scores(row, SQLITE_AUTO_AUTO6)
        name = row.get("name_auto") or row.get("name_expert")
    else:
        return AssessmentResult(
            cas=cas_display,
            acute=None,
            chronic=None,
            ecological=None,
            fate=None,
            atmospheric=None,
            physical=None,
            overall=None,
            source="not_found",
            name=row.get("name_expert") or row.get("name_auto"),
        )

    vals = [v for v in scores.values() if v is not None]
    overall = max_of_values(vals)

    return AssessmentResult(
        cas=cas_display,
        acute=scores["acute"],
        chronic=scores["chronic"],
        ecological=scores["ecological"],
        fate=scores["fate"],
        atmospheric=scores["atmospheric"],
        physical=scores["physical"],
        overall=overall,
        source=source,
        name=name,
    )
