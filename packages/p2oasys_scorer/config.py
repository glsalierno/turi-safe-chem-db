"""
Configuration for P2OASys scorer package.

Derived from GHaz8 packages/ghaz7_engine/config.py, with personal Windows paths
removed. Uses environment variables or repo-relative defaults.
"""

from __future__ import annotations

import os
from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parent
DATA_DIR = os.environ.get("P2OASYS_DATA_DIR", "").strip() or str(_PACKAGE_ROOT / "data")

P2OASYS_MATRIX_FILENAME = "Hazard Matrix Group Review 9-19-23.xlsx"
P2OASYS_MATRIX_PATH = os.environ.get(
    "P2OASYS_MATRIX_PATH", os.path.join(DATA_DIR, P2OASYS_MATRIX_FILENAME)
)

P2OASYS_IARC_CSV_PATH = os.environ.get(
    "P2OASYS_IARC_CSV", os.path.join(DATA_DIR, "iarc_by_cas.csv")
)
P2OASYS_ODP_GWP_CSV_PATH = os.environ.get(
    "P2OASYS_ODP_GWP_CSV", os.path.join(DATA_DIR, "odp_gwp_by_cas.csv")
)
P2OASYS_HAP_CSV_PATH = os.environ.get(
    "P2OASYS_HAP_CSV", os.path.join(DATA_DIR, "caa112b_hap_by_cas.csv")
)

CAMEO_NFPA_DB_PATH = os.environ.get(
    "CAMEO_NFPA_DB", os.path.join(DATA_DIR, "cameo_nfpa.sqlite")
)


def _resolve_atmo_dir() -> str:
    """Resolve ATMO_DIR: env var, then data/atmo."""
    env = os.environ.get("ATMO_DIR", "").strip()
    if env and os.path.isdir(env):
        return env
    local = os.path.join(DATA_DIR, "atmo")
    if os.path.isdir(local):
        return local
    return env or local


ATMO_DIR = _resolve_atmo_dir()

P2OASYS_SCORE_LOOKUP_DB = os.environ.get(
    "P2OASYS_SCORE_LOOKUP_DB", os.path.join(DATA_DIR, "p2oasys_score_lookup.sqlite")
)

OPERA_PRECOMPUTE_DB_PATH = os.environ.get(
    "OPERA_PRECOMPUTE_DB_PATH", os.path.join(DATA_DIR, "opera_precompute.sqlite")
)
