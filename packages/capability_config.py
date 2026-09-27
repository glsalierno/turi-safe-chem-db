"""
Centralized configuration for all capability data paths and feature switches.

This module is the SINGLE SOURCE OF TRUTH for:
  - Data directory paths (with repo-relative or user-data-dir defaults)
  - Feature enable/disable switches
  - Environment variable documentation

NO hard-coded personal paths. NO Path(__file__).parents[N] root-guessing
outside this module. Legacy env var names are aliased here.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Root paths (computed once; no guessing outside this module)
# ─────────────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
USER_CONFIG_DIR = Path.home() / ".turi-safe-chem-db"


def _env_path(key: str, *fallback_keys: str, default: Path | None = None) -> Path | None:
    """Get path from env var, supporting legacy aliases."""
    for k in (key,) + fallback_keys:
        val = os.environ.get(k, "").strip()
        if val:
            return Path(val)
    return default


def _env_bool(key: str, default: bool = False) -> bool:
    """Get boolean from env var (0/false/no/off = False, else True)."""
    val = os.environ.get(key, "").strip().lower()
    if not val:
        return default
    return val not in ("0", "false", "no", "off")


def _env_float(key: str, default: float) -> float:
    """Get float from env var."""
    val = os.environ.get(key, "").strip()
    if not val:
        return default
    try:
        return float(val)
    except ValueError:
        logger.warning("Invalid float for %s=%r, using default %s", key, val, default)
        return default


def _env_int(key: str, default: int) -> int:
    """Get int from env var."""
    val = os.environ.get(key, "").strip()
    if not val:
        return default
    try:
        return int(val)
    except ValueError:
        logger.warning("Invalid int for %s=%r, using default %s", key, val, default)
        return default


# ─────────────────────────────────────────────────────────────────────────────
# PubChem configuration
# ─────────────────────────────────────────────────────────────────────────────

class PubChemConfig:
    """PubChem API configuration."""

    @staticmethod
    def min_interval_s() -> float:
        """Minimum seconds between PubChem requests."""
        return _env_float("PUBCHEM_MIN_INTERVAL_S", 0.35)

    @staticmethod
    def max_retries() -> int:
        """Max retries on 429/503 before raising PubChemThrottledError."""
        return _env_int("PUBCHEM_MAX_RETRIES", 5)

    @staticmethod
    def cache_dir() -> Path:
        """PubChem response cache directory."""
        return _env_path("PUBCHEM_CACHE_DIR", default=DATA_DIR / "cache" / "pubchem") or (
            DATA_DIR / "cache" / "pubchem"
        )

    @staticmethod
    def cache_max_age_s() -> float:
        """Cache TTL in seconds."""
        return _env_float("PUBCHEM_CACHE_MAX_AGE_S", 86400.0)

    @staticmethod
    def bulk_dir() -> Path | None:
        """Directory for PubChem FTP bulk index (PR #7)."""
        return _env_path("PUBCHEM_BULK_DIR")

    @staticmethod
    def bulk_disabled() -> bool:
        """Whether bulk lookups are disabled."""
        return _env_bool("PUBCHEM_DISABLE_BULK", default=False)


# ─────────────────────────────────────────────────────────────────────────────
# P2OASys configuration
# ─────────────────────────────────────────────────────────────────────────────

class P2OASysConfig:
    """P2OASys scoring configuration."""

    @staticmethod
    def score_lookup_db() -> Path:
        """Path to P2OASys score lookup SQLite."""
        return _env_path("P2OASYS_SCORE_LOOKUP_DB", default=DATA_DIR / "p2oasys_score_lookup.sqlite") or (
            DATA_DIR / "p2oasys_score_lookup.sqlite"
        )

    @staticmethod
    def expert_csv() -> Path | None:
        """Path to optional expert CSV overlay."""
        return _env_path("EXPERT_P2OASYS_CSV")

    @staticmethod
    def matrix_dir() -> Path | None:
        """Directory for P2OASys hazard matrix data (PR #8)."""
        return _env_path("P2OASYS_MATRIX_DIR")


# ─────────────────────────────────────────────────────────────────────────────
# HSPiP configuration
# ─────────────────────────────────────────────────────────────────────────────

class HSPiPConfig:
    """HSPiP Hansen Solubility Parameters configuration."""

    @staticmethod
    def data_dir() -> Path | None:
        """Directory containing .sofx files (supports legacy HSPIP_DATA_DIR)."""
        return _env_path("HSPIP_DATA", "HSPIP_DATA_DIR")

    @staticmethod
    def exe_path() -> Path | None:
        """Path to HSPiP.exe or install folder (supports legacy HSPIP_PATH)."""
        return _env_path("HSPIP_EXE", "HSPIP_PATH")

    @staticmethod
    def teams_data_dir() -> Path | None:
        """Teams pack layout: sibling HSPiP_Data folder."""
        p = REPO_ROOT.parent / "HSPiP_Data"
        return p if p.is_dir() else None

    @staticmethod
    def teams_exe_dir() -> Path | None:
        """Teams pack layout: sibling HSPiP folder."""
        p = REPO_ROOT.parent / "HSPiP"
        return p if p.is_dir() else None


# ─────────────────────────────────────────────────────────────────────────────
# SDS enrichment configuration
# ─────────────────────────────────────────────────────────────────────────────

class SDSEnrichConfig:
    """SDS enrichment feature toggles."""

    @staticmethod
    def fisher_enabled() -> bool:
        """Whether Fisher SDS enrichment is enabled by default."""
        val = os.environ.get("DOSS_ENABLE_FISHER", "1").strip().lower()
        return val not in ("0", "false", "no", "off")

    @staticmethod
    def tci_enabled() -> bool:
        """Whether TCI SDS enrichment is enabled (always on for now)."""
        return True


# ─────────────────────────────────────────────────────────────────────────────
# Scorer reference tables (PR #8)
# ─────────────────────────────────────────────────────────────────────────────

class ScorerConfig:
    """Scorer hazard reference table paths (PR #8)."""

    @staticmethod
    def cameo_nfpa_db() -> Path | None:
        """Path to CAMEO NFPA SQLite."""
        return _env_path("CAMEO_NFPA_DB")

    @staticmethod
    def iarc_table() -> Path | None:
        """Path to IARC carcinogen table."""
        return _env_path("IARC_TABLE_PATH")

    @staticmethod
    def odp_gwp_table() -> Path | None:
        """Path to ODP/GWP atmospheric tables."""
        return _env_path("ODP_GWP_TABLE_PATH")

    @staticmethod
    def caa_hap_list() -> Path | None:
        """Path to CAA HAP list."""
        return _env_path("CAA_HAP_LIST_PATH")


# ─────────────────────────────────────────────────────────────────────────────
# External tools (PR #6, #9)
# ─────────────────────────────────────────────────────────────────────────────

class ExternalToolsConfig:
    """External tool paths (ECOSAR, IUCLID, CompTox, CPDB)."""

    @staticmethod
    def episuite_path() -> Path | None:
        """Path to EPI Suite installation (PR #6)."""
        return _env_path("EPISUITE_PATH")

    @staticmethod
    def ecosar_disabled() -> bool:
        """Whether ECOSAR is disabled."""
        return _env_bool("ECOSAR_DISABLE", default=False)

    @staticmethod
    def iuclid_api_url() -> str | None:
        """IUCLID API endpoint (PR #9)."""
        return os.environ.get("IUCLID_API_URL", "").strip() or None

    @staticmethod
    def iuclid_api_key() -> str | None:
        """IUCLID API key (PR #9)."""
        return os.environ.get("IUCLID_API_KEY", "").strip() or None

    @staticmethod
    def dsstox_cache_path() -> Path | None:
        """Path to DSSTox parquet/sqlite cache."""
        return _env_path("DSSTOX_CACHE_PATH")

    @staticmethod
    def epa_api_key() -> str | None:
        """EPA API key for ToxValDB."""
        return os.environ.get("EPA_API_KEY", "").strip() or None

    @staticmethod
    def cpdb_db_path() -> Path | None:
        """Path to CPDB sqlite database."""
        return _env_path("CPDB_DB_PATH")


# ─────────────────────────────────────────────────────────────────────────────
# Utility: get all config as dict (for reporting)
# ─────────────────────────────────────────────────────────────────────────────

def get_all_config() -> dict[str, Any]:
    """Return all configuration values for reporting."""
    return {
        "repo_root": str(REPO_ROOT),
        "data_dir": str(DATA_DIR),
        "user_config_dir": str(USER_CONFIG_DIR),
        "pubchem": {
            "min_interval_s": PubChemConfig.min_interval_s(),
            "max_retries": PubChemConfig.max_retries(),
            "cache_dir": str(PubChemConfig.cache_dir()),
            "cache_max_age_s": PubChemConfig.cache_max_age_s(),
            "bulk_dir": str(PubChemConfig.bulk_dir()) if PubChemConfig.bulk_dir() else None,
            "bulk_disabled": PubChemConfig.bulk_disabled(),
        },
        "p2oasys": {
            "score_lookup_db": str(P2OASysConfig.score_lookup_db()),
            "score_lookup_db_exists": P2OASysConfig.score_lookup_db().is_file(),
            "expert_csv": str(P2OASysConfig.expert_csv()) if P2OASysConfig.expert_csv() else None,
            "matrix_dir": str(P2OASysConfig.matrix_dir()) if P2OASysConfig.matrix_dir() else None,
        },
        "hspip": {
            "data_dir": str(HSPiPConfig.data_dir()) if HSPiPConfig.data_dir() else None,
            "exe_path": str(HSPiPConfig.exe_path()) if HSPiPConfig.exe_path() else None,
            "teams_data_dir": str(HSPiPConfig.teams_data_dir()) if HSPiPConfig.teams_data_dir() else None,
            "teams_exe_dir": str(HSPiPConfig.teams_exe_dir()) if HSPiPConfig.teams_exe_dir() else None,
        },
        "sds_enrich": {
            "fisher_enabled": SDSEnrichConfig.fisher_enabled(),
            "tci_enabled": SDSEnrichConfig.tci_enabled(),
        },
        "scorer": {
            "cameo_nfpa_db": str(ScorerConfig.cameo_nfpa_db()) if ScorerConfig.cameo_nfpa_db() else None,
            "iarc_table": str(ScorerConfig.iarc_table()) if ScorerConfig.iarc_table() else None,
            "odp_gwp_table": str(ScorerConfig.odp_gwp_table()) if ScorerConfig.odp_gwp_table() else None,
            "caa_hap_list": str(ScorerConfig.caa_hap_list()) if ScorerConfig.caa_hap_list() else None,
        },
        "external_tools": {
            "episuite_path": str(ExternalToolsConfig.episuite_path()) if ExternalToolsConfig.episuite_path() else None,
            "ecosar_disabled": ExternalToolsConfig.ecosar_disabled(),
            "iuclid_api_url": ExternalToolsConfig.iuclid_api_url(),
            "iuclid_api_key_set": bool(ExternalToolsConfig.iuclid_api_key()),
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Environment variable documentation (for CAPABILITIES.md generation)
# ─────────────────────────────────────────────────────────────────────────────

ENV_VAR_DOCS: dict[str, dict[str, str]] = {
    "PUBCHEM_MIN_INTERVAL_S": {
        "purpose": "Minimum seconds between PubChem requests",
        "default": "0.35",
    },
    "PUBCHEM_MAX_RETRIES": {
        "purpose": "Max retries on 429/503 before raising PubChemThrottledError",
        "default": "5",
    },
    "PUBCHEM_CACHE_DIR": {
        "purpose": "PubChem response cache directory",
        "default": "data/cache/pubchem/",
    },
    "PUBCHEM_CACHE_MAX_AGE_S": {
        "purpose": "Cache TTL in seconds",
        "default": "86400",
    },
    "PUBCHEM_BULK_DIR": {
        "purpose": "Directory for PubChem FTP bulk index",
        "default": "(none)",
    },
    "PUBCHEM_DISABLE_BULK": {
        "purpose": "Set 1 to disable bulk lookups",
        "default": "0",
    },
    "P2OASYS_SCORE_LOOKUP_DB": {
        "purpose": "Path to P2OASys score lookup SQLite",
        "default": "data/p2oasys_score_lookup.sqlite",
    },
    "EXPERT_P2OASYS_CSV": {
        "purpose": "Path to optional expert CSV overlay",
        "default": "(none)",
    },
    "P2OASYS_MATRIX_DIR": {
        "purpose": "Directory for P2OASys hazard matrix data",
        "default": "(none)",
    },
    "HSPIP_DATA": {
        "purpose": "Directory containing .sofx files",
        "default": "(none)",
    },
    "HSPIP_DATA_DIR": {
        "purpose": "Alias for HSPIP_DATA",
        "default": "(none)",
    },
    "HSPIP_EXE": {
        "purpose": "Path to HSPiP.exe or install folder",
        "default": "(none)",
    },
    "HSPIP_PATH": {
        "purpose": "Alias for HSPIP_EXE",
        "default": "(none)",
    },
    "DOSS_ENABLE_FISHER": {
        "purpose": "Default for Fisher SDS toggle",
        "default": "1",
    },
    "CAMEO_NFPA_DB": {
        "purpose": "Path to CAMEO NFPA SQLite",
        "default": "(none)",
    },
    "IARC_TABLE_PATH": {
        "purpose": "Path to IARC carcinogen table",
        "default": "(none)",
    },
    "ODP_GWP_TABLE_PATH": {
        "purpose": "Path to ODP/GWP atmospheric tables",
        "default": "(none)",
    },
    "CAA_HAP_LIST_PATH": {
        "purpose": "Path to CAA HAP list",
        "default": "(none)",
    },
    "EPISUITE_PATH": {
        "purpose": "Path to EPI Suite installation",
        "default": "(none)",
    },
    "ECOSAR_DISABLE": {
        "purpose": "Set 1 to disable ECOSAR",
        "default": "0",
    },
    "IUCLID_API_URL": {
        "purpose": "IUCLID API endpoint",
        "default": "(none)",
    },
    "IUCLID_API_KEY": {
        "purpose": "IUCLID API key",
        "default": "(none)",
    },
    "PYTHONPATH": {
        "purpose": "Set to repo root if not using editable install",
        "default": "(none)",
    },
}
