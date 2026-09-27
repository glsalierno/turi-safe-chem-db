"""
Configuration for IUCLID dossier access.

Environment Variables:
    IUCLID_ENABLED          - Enable/disable: "true"/"false"/"auto" (default: auto)
    IUCLID_DOSSIER_SOURCE   - Path to extracted dossiers folder or bulk .zip
    IUCLID_DOSSIER_INDEX    - Path to dossier_info .xlsx or prebuilt .sqlite index
    IUCLID_FORMAT_DIR       - Path to IUCLID format pack (optional, for phrase labels)
    IUCLID_CACHE_DIR        - Cache location (default: ~/.turi-safe-chem-db/iuclid_cache)

    Legacy names (supported as aliases):
    OFFLINE_LOCAL_ARCHIVE      - Alias for IUCLID_DOSSIER_SOURCE
    OFFLINE_DOSSIER_INFO_XLSX  - Alias for IUCLID_DOSSIER_INDEX
    OFFLINE_IUCLID_FORMAT_DIR  - Alias for IUCLID_FORMAT_DIR
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

_config_logged = False


@dataclass(frozen=True)
class IUCLIDConfig:
    """Immutable configuration for IUCLID access."""
    
    enabled: bool
    dossier_source: Path | None
    dossier_index: Path | None
    format_dir: Path | None
    cache_dir: Path
    disable_reason: str | None = None


def _get_env(primary: str, *aliases: str, default: str = "") -> str:
    """Get env var with fallback aliases."""
    val = os.environ.get(primary, "").strip()
    if val:
        return val
    for alias in aliases:
        val = os.environ.get(alias, "").strip()
        if val:
            return val
    return default


def _resolve_path(val: str) -> Path | None:
    """Resolve a path string to Path, returning None if empty or nonexistent."""
    if not val:
        return None
    p = Path(val).expanduser()
    if p.exists():
        return p.resolve()
    return None


def _default_cache_dir() -> Path:
    """Get default cache directory."""
    base = Path.home() / ".turi-safe-chem-db" / "iuclid_cache"
    base.mkdir(parents=True, exist_ok=True)
    return base


def get_config() -> IUCLIDConfig:
    """
    Get IUCLID configuration from environment variables.
    
    Logs ONE clear message when IUCLID is disabled, never silently skips.
    """
    global _config_logged
    
    enabled_str = _get_env("IUCLID_ENABLED", default="auto").lower()
    
    dossier_source_str = _get_env(
        "IUCLID_DOSSIER_SOURCE",
        "OFFLINE_LOCAL_ARCHIVE",
    )
    dossier_source = _resolve_path(dossier_source_str)
    
    dossier_index_str = _get_env(
        "IUCLID_DOSSIER_INDEX",
        "OFFLINE_DOSSIER_INFO_XLSX",
    )
    dossier_index = _resolve_path(dossier_index_str)
    
    format_dir_str = _get_env(
        "IUCLID_FORMAT_DIR",
        "OFFLINE_IUCLID_FORMAT_DIR",
    )
    format_dir = _resolve_path(format_dir_str)
    
    cache_dir_str = _get_env("IUCLID_CACHE_DIR")
    if cache_dir_str:
        cache_dir = Path(cache_dir_str).expanduser()
        cache_dir.mkdir(parents=True, exist_ok=True)
    else:
        cache_dir = _default_cache_dir()
    
    disable_reason: str | None = None
    
    if enabled_str == "false":
        enabled = False
        disable_reason = "IUCLID_ENABLED=false"
    elif enabled_str == "true":
        if dossier_source is None:
            enabled = False
            if dossier_source_str:
                disable_reason = f"IUCLID_DOSSIER_SOURCE path not found: {dossier_source_str}"
            else:
                disable_reason = "IUCLID_DOSSIER_SOURCE not set"
        else:
            enabled = True
    else:
        if dossier_source is None:
            enabled = False
            if dossier_source_str:
                disable_reason = f"IUCLID disabled: IUCLID_DOSSIER_SOURCE path not found: {dossier_source_str}"
            else:
                disable_reason = "IUCLID disabled: IUCLID_DOSSIER_SOURCE not set"
        else:
            enabled = True
    
    if disable_reason and not _config_logged:
        logger.info(disable_reason)
        _config_logged = True
    
    return IUCLIDConfig(
        enabled=enabled,
        dossier_source=dossier_source,
        dossier_index=dossier_index,
        format_dir=format_dir,
        cache_dir=cache_dir,
        disable_reason=disable_reason,
    )


def is_enabled() -> bool:
    """Check if IUCLID access is enabled and configured."""
    return get_config().enabled


def get_status() -> dict:
    """
    Get detailed IUCLID configuration status.
    
    Returns a dict with:
        enabled: bool
        dossier_source: str | None (path)
        dossier_index: str | None (path)
        format_dir: str | None (path)
        cache_dir: str (path)
        disable_reason: str | None
        dossier_count: int | None (if source is configured)
    """
    config = get_config()
    
    status = {
        "enabled": config.enabled,
        "dossier_source": str(config.dossier_source) if config.dossier_source else None,
        "dossier_index": str(config.dossier_index) if config.dossier_index else None,
        "format_dir": str(config.format_dir) if config.format_dir else None,
        "cache_dir": str(config.cache_dir),
        "disable_reason": config.disable_reason,
        "dossier_count": None,
    }
    
    if config.dossier_source:
        try:
            if config.dossier_source.suffix.lower() == ".zip":
                import zipfile
                with zipfile.ZipFile(config.dossier_source) as zf:
                    status["dossier_count"] = sum(
                        1 for n in zf.namelist() if n.endswith(".i6z")
                    )
            elif config.dossier_source.is_dir():
                status["dossier_count"] = sum(
                    1 for _ in config.dossier_source.rglob("*.i6z")
                )
        except Exception:
            pass
    
    return status


def reset_config_log() -> None:
    """Reset the config logged flag (for testing)."""
    global _config_logged
    _config_logged = False
