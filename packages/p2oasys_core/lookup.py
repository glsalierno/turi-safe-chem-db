"""
P2OASys overall score lookup for DoSS on-demand (slim, no GHaz7 import).

Sources (priority):
  1. Expert CSV — EXPERT_P2OASYS_CSV env, sidebar upload, or
     ``priority_expert_p2oasys_scores.csv`` next to the app (62-set overlay).
  2. Bundled ``data/p2oasys_score_lookup.sqlite`` expert Auto6 (harvest single-CAS).
  3. Same SQLite auto Auto6 / auto_overall for CAS with no expert row.

Overall convention: max of Auto6 category maxima (Acute, Chronic, Ecological,
Fate & Transport, Atmospheric, Physical). Process / Life Cycle are not included
in Auto6. SQLite ``expert_overall`` is a *mean* and is intentionally ignored.
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
DEFAULT_LOOKUP_DB = _BUNDLED_LOOKUP_DB

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


def overall_from_auto6_maxes(row: pd.Series | dict) -> Optional[float]:
    """Max of Auto6 ``*_max`` columns present on an expert CSV row."""
    vals: list[float] = []
    getter = row.get if isinstance(row, dict) else row.get
    # Also accept case-insensitive / alternate spellings
    cols = list(AUTO6_MAX_COLS)
    if not isinstance(row, dict):
        for c in row.index:
            cl = str(c).lower()
            if cl.endswith("_max") and any(
                k.split("_max")[0].lower() in cl
                for k in AUTO6_MAX_COLS
            ):
                if c not in cols and "process" not in cl and "life_cycle" not in cl and "lifecycle" not in cl:
                    # stick to explicit Auto6 list only
                    pass
    for col in AUTO6_MAX_COLS:
        v = getter(col) if callable(getter) else None
        if v is None and not isinstance(row, dict):
            # try lowercase match
            for c in row.index:
                if str(c).strip() == col:
                    v = row[c]
                    break
        f = _to_float(v)
        if f is not None:
            vals.append(f)
    return max_of_values(vals)


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
    overall = overall_from_auto6_maxes(row)
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
    overall = max_of_values(vals)
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


def documented_paths() -> dict[str, str]:
    """Paths used by this module (for README / UI captions)."""
    resolved = default_lookup_db_path()
    return {
        "default_expert_csv": str(DEFAULT_EXPERT_CSV),
        "ghaaz7_lookup_db": str(resolved),
        "lookup_db_example_relative": str(_EXAMPLE_RELATIVE_LOOKUP_DB),
        "env_expert_csv": "EXPERT_P2OASYS_CSV",
        "env_lookup_db": "P2OASYS_SCORE_LOOKUP_DB",
    }
