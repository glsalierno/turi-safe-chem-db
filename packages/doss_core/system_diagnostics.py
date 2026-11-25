"""Safe, read-only diagnostics for the Streamlit sidebar."""

import os
import platform
import sqlite3
from contextlib import closing
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from packages.doss_core.logging_support import get_logger
from packages.p2oasys_core.lookup import DEFAULT_LOOKUP_DB

logger = get_logger(__name__)


def dependency_versions(app_name: str, source_version: str) -> dict[str, str]:
    versions = {"Python": platform.python_version()}
    for name in (app_name, "streamlit", "pandas", "requests", "pypdf", "rdkit"):
        try:
            versions[name] = version(name)
        except PackageNotFoundError:
            versions[name] = source_version if name == app_name else "not installed"
    return versions


def bundled_database(path: Path = DEFAULT_LOOKUP_DB) -> dict[str, str | int]:
    if not path.is_file():
        return {"status": "missing"}
    try:
        with path.open("rb") as handle:
            if handle.read(16) != b"SQLite format 3\x00":
                return {"status": "present but not SQLite"}
        uri = path.resolve().as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=1)) as db:
            row = db.execute("SELECT COUNT(*) FROM by_cas").fetchone()
            return {"status": "available", "rows": int(row[0])}
    except (OSError, sqlite3.Error) as exc:
        logger.warning("diagnostics_database_unavailable error_type=%s", type(exc).__name__)
        return {"status": "present but unreadable"}


def active_overrides(names: tuple[str, ...]) -> list[str]:
    """Only expose allowlisted variable names, never their values."""
    return [name for name in names if os.environ.get(name, "").strip()]
