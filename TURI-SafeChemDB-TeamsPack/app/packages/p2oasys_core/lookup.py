"""
P2OASys overall score lookup for DoSS on-demand (slim, no GHaz7 import).

Sources (priority):
  1. Expert CSV — EXPERT_P2OASYS_CSV env, sidebar upload, or
     ``priority_expert_p2oasys_scores.csv`` next to the app (62-set overlay).
  2. Bundled ``data/p2oasys_score_lookup.sqlite`` expert Auto6 (harvest single-CAS).
  3. Same SQLite auto Auto6 / auto_overall for CAS with no expert row.

Expert overall (matches p2oasys.turi.org ``evaluation`` / ``p2oasys_score``):
  prefer an explicit evaluation column on the expert CSV; else the **mean** of
  available Auto6 category maxima. Process / Life Cycle are not in Auto6.

Auto overall (draft screen): **max** of Auto6 auto category scores (precautionary).
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Optional

import pandas as pd

# Monorepo roots: packages/p2oasys_core/lookup.py -> repo root
PKG_DIR = Path(__file__).resolve().parent
REPO_ROOT = PKG_DIR.parents[1]
DATA_DIR = REPO_ROOT / "data"
# APP_DIR aliases DATA_DIR so fisher/tci catalog paths (APP_DIR / "*.csv") resolve to data/
APP_DIR = DATA_DIR
DEFAULT_EXPERT_CSV = DATA_DIR / "priority_expert_p2oasys_scores.csv"

# Optional relative sibling GHaz7 tree (no usernames) — TCI catalog/SDS cache hints only.
# Example relative layout: ../GHhaz6/GHaz7/quick-hazard-assessment-app/
# TCI SDS enrichment (packages.doss_core.tci) intentionally uses this for optional local caches.
GHAZ7_ROOT = (
    REPO_ROOT.parent
    / "GHhaz6"
    / "GHaz7"
    / "quick-hazard-assessment-app"
)
# SQLite score lookup: env P2OASYS_SCORE_LOOKUP_DB, then bundled data/, then sibling GHaz7.
_BUNDLED_LOOKUP_DB = DATA_DIR / "p2oasys_score_lookup.sqlite"
_EXAMPLE_RELATIVE_LOOKUP_DB = GHAZ7_ROOT / "data" / "p2oasys_score_lookup.sqlite"

# Auto6 category max columns in the priority expert export CSV.
AUTO6_MAX_COLS = (
    "Acute_Human_Effects_max",
    "Chronic_Human_Effects_max",
    "Ecological_Hazards_max",
    "Environmental_Fate_and_Transport_max",
    "Atmospheric_Hazard_max",
    "Physical_Properties_max",
)

# SQLite Auto6 category columns (expert / auto).
SQLITE_EXPERT_AUTO6 = (
    "expert_acute",
    "expert_chronic",
    "expert_ecological",
    "expert_fate",
    "expert_atmospheric",
    "expert_physical",
)
SQLITE_AUTO_AUTO6 = (
    "auto_acute",
    "auto_chronic",
    "auto_ecological",
    "auto_fate",
    "auto_atmospheric",
    "auto_physical",
)

EMPTY = "-"


def normalize_cas(cas: str | None) -> str:
    if not cas:
        return ""
    return "".join(c for c in str(cas) if c.isdigit())


def format_cas_display(cas: str | None) -> str:
    digits = normalize_cas(cas)
    if not digits:
        return (cas or "").strip()
    if len(digits) >= 5:
        return f"{digits[:-3]}-{digits[-3:-1]}-{digits[-1]}"
    return digits


def _to_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        if isinstance(v, float) and pd.isna(v):
            return None
    except Exception:
        pass
    try:
        return float(v)
    except (TypeError, ValueError):
        s = str(v).strip()
        if not s or s.lower() in ("nan", "none", "null", "-", ""):
            return None
        try:
            return float(s)
        except ValueError:
            return None


def max_of_values(values: list[float]) -> Optional[float]:
    nums = [v for v in values if v is not None]
    if not nums:
        return None
    return max(nums)


def mean_of_values(values: list[float]) -> Optional[float]:
    nums = [v for v in values if v is not None]
    if not nums:
        return None
    return sum(nums) / len(nums)


_EVALUATION_COL_ALIASES = (
    "evaluation",
    "p2oasys_score",
    "p2oasys_overall",
    "overall_evaluation",
    "expert_overall",
    "overall",
)


def _auto6_category_maxes(row: pd.Series | dict) -> list[float]:
    """Collect Auto6 ``*_max`` values from an expert CSV row."""
    vals: list[float] = []
    getter = row.get if isinstance(row, dict) else row.get
    for col in AUTO6_MAX_COLS:
        v = getter(col) if callable(getter) else None
        if v is None and not isinstance(row, dict):
            for c in row.index:
                if str(c).strip() == col:
                    v = row[c]
                    break
        f = _to_float(v)
        if f is not None:
            vals.append(f)
    return vals


def overall_from_expert_row(row: pd.Series | dict) -> Optional[float]:
    """Expert overall matching the curated site score when possible.

    Prefer an explicit evaluation / p2oasys_score column. Otherwise mean of
    available Auto6 category maxima (not max).
    """
    getter = row.get if isinstance(row, dict) else row.get
    if isinstance(row, dict):
        keys = [str(k) for k in row.keys()]
    else:
        keys = [str(c) for c in row.index]
    lower_map = {k.lower().strip(): k for k in keys}
    for alias in _EVALUATION_COL_ALIASES:
        key = lower_map.get(alias)
        if not key:
            continue
        raw = getter(key) if callable(getter) else row[key]
        f = _to_float(raw)
        if f is not None:
            return f
    return mean_of_values(_auto6_category_maxes(row))


def default_lookup_db_path() -> Path:
    """Resolve score-lookup SQLite path.

    Prefer ``P2OASYS_SCORE_LOOKUP_DB``. Else the bundled
    ``data/p2oasys_score_lookup.sqlite`` if present, else the sibling GHaz7
    example path (may not exist). Never a user home directory.
    """
    env = (os.environ.get("P2OASYS_SCORE_LOOKUP_DB") or "").strip()
    if env:
        return Path(env)
    if _BUNDLED_LOOKUP_DB.is_file():
        return _BUNDLED_LOOKUP_DB
    return _EXAMPLE_RELATIVE_LOOKUP_DB


def load_expert_csv(path: Path | str | None = None) -> Optional[pd.DataFrame]:
    """Load expert P2OASys CSV from explicit path, env, or app-dir default."""
    candidates: list[Path] = []
    if path:
        candidates.append(Path(path))
    env = (os.environ.get("EXPERT_P2OASYS_CSV") or "").strip()
    if env:
        candidates.append(Path(env))
    candidates.append(DEFAULT_EXPERT_CSV)
    for p in candidates:
        if p and p.is_file():
            try:
                df = pd.read_csv(p)
                # Normalize cas column name
                cols_lower = {c.lower(): c for c in df.columns}
                if "cas" in cols_lower and cols_lower["cas"] != "cas":
                    df = df.rename(columns={cols_lower["cas"]: "cas"})
                if "cas" not in df.columns:
                    return None
                df["cas"] = df["cas"].astype(str).str.strip()
                df["_cas_digits"] = df["cas"].map(normalize_cas)
                return df
            except Exception:
                continue
    return None


def lookup_expert_csv(cas: str, expert_df: Optional[pd.DataFrame]) -> Optional[dict[str, Any]]:
    if expert_df is None or expert_df.empty:
        return None
    key = normalize_cas(cas)
    if not key:
        return None
    if "_cas_digits" in expert_df.columns:
        match = expert_df[expert_df["_cas_digits"] == key]
    else:
        match = expert_df[expert_df["cas"].map(normalize_cas) == key]
    if match.empty:
        return None
    row = match.iloc[0]
    overall = overall_from_expert_row(row)
    if overall is None:
        return None
    return {
        "overall": overall,
        "source": "expert",
        "detail": "expert_csv",
        "name": str(row.get("name") or "") or None,
    }


def _sqlite_row(cas: str, db_path: Path | str | None = None) -> Optional[dict[str, Any]]:
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


def lookup_sqlite_expert(cas: str, db_path: Path | str | None = None) -> Optional[dict[str, Any]]:
    row = _sqlite_row(cas, db_path)
    if not row or not row.get("has_expert"):
        return None
    vals = [_to_float(row.get(c)) for c in SQLITE_EXPERT_AUTO6]
    vals = [v for v in vals if v is not None]
    # Mean of Auto6 category maxima ≈ site evaluation (not max; not stale expert_overall).
    overall = mean_of_values(vals)
    if overall is None:
        return None
    return {
        "overall": overall,
        "source": "expert",
        "detail": f"sqlite:{default_lookup_db_path().name}",
        "name": row.get("name_expert"),
    }


def lookup_sqlite_auto(cas: str, db_path: Path | str | None = None) -> Optional[dict[str, Any]]:
    row = _sqlite_row(cas, db_path)
    if not row or not row.get("has_auto"):
        return None
    vals = [_to_float(row.get(c)) for c in SQLITE_AUTO_AUTO6]
    vals = [v for v in vals if v is not None]
    overall = max_of_values(vals)
    if overall is None:
        overall = _to_float(row.get("auto_overall"))
    if overall is None:
        return None
    return {
        "overall": overall,
        "source": "auto",
        "detail": f"sqlite:{default_lookup_db_path().name}",
        "name": row.get("name_auto"),
    }


def resolve_p2oasys(
    cas: str,
    expert_df: Optional[pd.DataFrame] = None,
    *,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """
    Resolve P2OASys overall + source for a CAS.

    Returns dict with keys:
      overall (str|float display), source ('expert'|'auto'|'-'), detail (str)
    """
    hit = lookup_expert_csv(cas, expert_df)
    if hit is None:
        hit = lookup_sqlite_expert(cas, db_path)
    if hit is None:
        hit = lookup_sqlite_auto(cas, db_path)

    if hit is None:
        return {"overall": EMPTY, "source": EMPTY, "detail": "not_found"}

    overall = hit["overall"]
    # Display as int when whole number, else one decimal
    if abs(overall - round(overall)) < 1e-9:
        overall_str = str(int(round(overall)))
    else:
        overall_str = str(round(overall, 1))

    return {
        "overall": overall_str,
        "source": hit["source"],
        "detail": hit.get("detail") or hit["source"],
        "name": hit.get("name"),
    }



def load_cas_catalog(db_path: Path | str | None = None) -> list[dict[str, str]]:
    """Load CAS + name catalog from the bundled score-lookup SQLite.

    Returns list of dicts with keys: cas, name (best available from expert/auto),
    has_expert, has_auto. Sorted by CAS. Used for UI searchable dropdowns.
    """
    path = Path(db_path) if db_path else default_lookup_db_path()
    if not path.is_file():
        return []
    try:
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """SELECT cas, name_expert, name_auto, has_expert, has_auto
                   FROM by_cas ORDER BY cas"""
            ).fetchall()
            result = []
            for row in rows:
                name = row["name_expert"] or row["name_auto"] or ""
                result.append({
                    "cas": row["cas"],
                    "name": name,
                    "has_expert": bool(row["has_expert"]),
                    "has_auto": bool(row["has_auto"]),
                })
            return result
        finally:
            conn.close()
    except Exception:
        return []

def cas_catalog_count(db_path: Path | str | None = None) -> int:
    """Return count of CAS entries in the bundled score-lookup SQLite."""
    path = Path(db_path) if db_path else default_lookup_db_path()
    if not path.is_file():
        return 0
    try:
        conn = sqlite3.connect(str(path))
        try:
            count = conn.execute("SELECT COUNT(*) FROM by_cas").fetchone()[0]
            return count
        finally:
            conn.close()
    except Exception:
        return 0
