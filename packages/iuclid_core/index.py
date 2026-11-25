"""
IUCLID dossier index: CAS → UUID mapping and dossier path resolution.

Supports:
1. ECHA dossier_info XLSX (reach_study_results-dossier_info_*.xlsx)
2. CSV export of the same
3. Pre-built SQLite index
4. Scanning a dossier folder
"""

from __future__ import annotations

import csv
import io
import logging
import re
import sqlite3
import zipfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def normalize_cas(cas: str) -> str:
    """
    Normalize a CAS number to ###-##-# format.
    
    Handles formats like '71-43-2', '071-43-2', '71432', etc.
    """
    if not cas:
        return ""
    digits = re.sub(r"[^\d]", "", cas)
    if len(digits) < 5:
        return cas
    check = digits[-1]
    reg = digits[-3:-1]
    seq = digits[:-3].lstrip("0") or "0"
    return f"{seq}-{reg}-{check}"


def _load_xlsx_index(xlsx_path: Path) -> dict[str, list[str]]:
    """
    Load CAS → [UUID] mapping from ECHA dossier_info XLSX.
    
    Expects columns: DOSSIER UUID (Dossier), CAS_NUMBER (Ref. sub.)
    """
    try:
        import openpyxl
    except ImportError:
        logger.warning(
            "openpyxl not installed, cannot load XLSX index. "
            "Install with: pip install openpyxl"
        )
        return {}
    
    cas_to_uuids: dict[str, list[str]] = {}
    
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    
    target_sheet = None
    for sheet_name in wb.sheetnames:
        if "REACH Study Results" in sheet_name or "23-05" in sheet_name:
            target_sheet = sheet_name
            break
    if target_sheet is None:
        target_sheet = wb.sheetnames[0]
    
    ws = wb[target_sheet]
    rows = ws.iter_rows(values_only=True)
    
    try:
        header = next(rows)
    except StopIteration:
        return {}
    
    uuid_col = None
    cas_col = None
    for i, h in enumerate(header):
        h_str = str(h or "").upper()
        if "DOSSIER UUID" in h_str or h_str == "UUID":
            uuid_col = i
        elif "CAS_NUMBER" in h_str or "CAS" in h_str:
            cas_col = i
    
    if uuid_col is None or cas_col is None:
        logger.warning(
            "Could not find UUID/CAS columns in %s (header: %s)",
            xlsx_path,
            header,
        )
        return {}
    
    for row in rows:
        if len(row) <= max(uuid_col, cas_col):
            continue
        uuid = str(row[uuid_col] or "").strip()
        cas = str(row[cas_col] or "").strip()
        if uuid and cas:
            norm = normalize_cas(cas)
            if norm:
                if norm not in cas_to_uuids:
                    cas_to_uuids[norm] = []
                if uuid not in cas_to_uuids[norm]:
                    cas_to_uuids[norm].append(uuid)
    
    wb.close()
    return cas_to_uuids


def _load_csv_index(csv_path: Path) -> dict[str, list[str]]:
    """
    Load CAS → [UUID] mapping from CSV.
    
    Expects columns containing 'uuid' and 'cas' (case-insensitive).
    """
    cas_to_uuids: dict[str, list[str]] = {}
    
    with open(csv_path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        
        uuid_field = None
        cas_field = None
        for field in reader.fieldnames or []:
            fl = field.lower()
            if "uuid" in fl or "dossier" in fl:
                uuid_field = field
            elif "cas" in fl:
                cas_field = field
        
        if uuid_field is None or cas_field is None:
            logger.warning(
                "Could not find UUID/CAS columns in %s (fields: %s)",
                csv_path,
                reader.fieldnames,
            )
            return {}
        
        for row in reader:
            uuid = row.get(uuid_field, "").strip()
            cas = row.get(cas_field, "").strip()
            if uuid and cas:
                norm = normalize_cas(cas)
                if norm:
                    if norm not in cas_to_uuids:
                        cas_to_uuids[norm] = []
                    if uuid not in cas_to_uuids[norm]:
                        cas_to_uuids[norm].append(uuid)
    
    return cas_to_uuids


def _load_sqlite_index(db_path: Path) -> dict[str, list[str]]:
    """
    Load CAS → [UUID] mapping from SQLite index.
    
    Expects table: cas_to_uuid(cas TEXT, uuid TEXT)
    """
    cas_to_uuids: dict[str, list[str]] = {}
    
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='cas_to_uuid'"
        )
        if cursor.fetchone() is None:
            return {}
        
        for cas, uuid in conn.execute("SELECT cas, uuid FROM cas_to_uuid"):
            norm = normalize_cas(cas)
            if norm:
                if norm not in cas_to_uuids:
                    cas_to_uuids[norm] = []
                if uuid not in cas_to_uuids[norm]:
                    cas_to_uuids[norm].append(uuid)
    finally:
        conn.close()
    
    return cas_to_uuids


_index_cache: dict[str, list[str]] | None = None


def load_index(index_path: Path | None = None) -> dict[str, list[str]]:
    """
    Load CAS → [UUID] index from configured source.
    
    Supports .xlsx, .csv, and .sqlite files.
    Caches result for subsequent calls.
    """
    global _index_cache
    
    if _index_cache is not None:
        return _index_cache
    
    if index_path is None:
        from packages.iuclid_core.config import get_config
        config = get_config()
        index_path = config.dossier_index
    
    if index_path is None:
        logger.debug("No dossier index configured")
        return {}
    
    suffix = index_path.suffix.lower()
    if suffix in (".xlsx", ".xls"):
        _index_cache = _load_xlsx_index(index_path)
    elif suffix == ".csv":
        _index_cache = _load_csv_index(index_path)
    elif suffix in (".sqlite", ".db", ".sqlite3"):
        _index_cache = _load_sqlite_index(index_path)
    else:
        logger.warning("Unknown index file format: %s", index_path)
        _index_cache = {}
    
    logger.debug(
        "Loaded index from %s: %d CAS numbers, %d UUIDs",
        index_path,
        len(_index_cache),
        sum(len(v) for v in _index_cache.values()),
    )
    
    return _index_cache


def get_dossier_uuids_for_cas(
    cas: str, index_path: Path | None = None
) -> list[str]:
    """Get all dossier UUIDs for a CAS number."""
    index = load_index(index_path)
    norm = normalize_cas(cas)
    return index.get(norm, [])


def get_dossier_path(
    uuid: str, dossier_source: Path | None = None
) -> Path | io.BytesIO | None:
    """
    Get path to a dossier by UUID.
    
    If dossier_source is a directory, searches for <uuid>.i6z.
    If dossier_source is a zip file, returns BytesIO of the nested .i6z.
    """
    if dossier_source is None:
        from packages.iuclid_core.config import get_config
        dossier_source = get_config().dossier_source
    
    if dossier_source is None:
        return None
    
    uuid_lower = uuid.lower()
    
    if dossier_source.is_dir():
        for pattern in [f"{uuid}.i6z", f"{uuid_lower}.i6z", f"*{uuid}*.i6z"]:
            matches = list(dossier_source.rglob(pattern))
            if matches:
                return matches[0]
        return None
    
    if dossier_source.suffix.lower() == ".zip":
        try:
            with zipfile.ZipFile(dossier_source) as outer_zf:
                for name in outer_zf.namelist():
                    if uuid_lower in name.lower() and name.endswith(".i6z"):
                        return io.BytesIO(outer_zf.read(name))
        except zipfile.BadZipFile:
            logger.warning("Bad zip file: %s", dossier_source)
    
    return None


def build_sqlite_index(
    index_source: Path,
    output_path: Path,
    dossier_source: Path | None = None,
) -> int:
    """
    Build a SQLite index from xlsx/csv source.
    
    Returns number of CAS-UUID mappings created.
    """
    suffix = index_source.suffix.lower()
    if suffix in (".xlsx", ".xls"):
        cas_to_uuids = _load_xlsx_index(index_source)
    elif suffix == ".csv":
        cas_to_uuids = _load_csv_index(index_source)
    else:
        raise ValueError(f"Unsupported index source format: {suffix}")
    
    conn = sqlite3.connect(output_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cas_to_uuid (
                cas TEXT NOT NULL,
                uuid TEXT NOT NULL,
                PRIMARY KEY (cas, uuid)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cas ON cas_to_uuid(cas)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_uuid ON cas_to_uuid(uuid)")
        
        count = 0
        for cas, uuids in cas_to_uuids.items():
            for uuid in uuids:
                conn.execute(
                    "INSERT OR IGNORE INTO cas_to_uuid (cas, uuid) VALUES (?, ?)",
                    (cas, uuid),
                )
                count += 1
        
        conn.commit()
        return count
    finally:
        conn.close()


def reset_index_cache() -> None:
    """Reset cached index (for testing)."""
    global _index_cache
    _index_cache = None
