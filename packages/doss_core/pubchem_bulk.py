"""
PubChem FTP/HTTPS bulk index for local CAS → CID lookups.

Downloads and indexes PubChem bulk files to reduce API calls:
  - CID-Synonym-filtered.gz — CAS → CID mappings
  - CID-SMILES.gz — CID → SMILES
  - CID-Title.gz — CID → compound name
  - CID-InChI-Key.gz — CID → InChI key

The bulk files are multi-GB; they are streamed line-by-line
(bounded memory, never loaded entirely) and stored in a user data directory.

Usage:
    python -m packages.doss_core.pubchem_bulk build    # Download and build index
    python -m packages.doss_core.pubchem_bulk refresh  # Check and update if stale
    python -m packages.doss_core.pubchem_bulk status   # Show index stats

Environment variables:
    PUBCHEM_BULK_DIR       Override bulk data directory (default ~/.turi-safe-chem-db/pubchem-bulk/)
    PUBCHEM_DISABLE_BULK   Set to 1 to skip bulk lookup entirely
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, Optional, Tuple
from urllib.parse import urlparse

import requests

PUBCHEM_FTP_BASE = "https://ftp.ncbi.nlm.nih.gov/pubchem/Compound/Extras"

BULK_FILES = {
    "synonyms": "CID-Synonym-filtered.gz",
    "smiles": "CID-SMILES.gz",
    "title": "CID-Title.gz",
    "inchikey": "CID-InChI-Key.gz",
}

CAS_PATTERN = re.compile(r"^\d{1,7}-\d{2}-\d$")

REFRESH_INTERVAL_DAYS = 30
CHUNK_SIZE = 8 * 1024 * 1024
REQUEST_TIMEOUT = 60
MAX_DOWNLOAD_RETRIES = 3

_bulk_dir: Path | None = None
_bulk_disabled: bool | None = None


def _get_bulk_dir() -> Path:
    """Return bulk data directory, creating if needed."""
    global _bulk_dir
    if _bulk_dir is not None:
        return _bulk_dir

    env_dir = os.environ.get("PUBCHEM_BULK_DIR")
    if env_dir:
        _bulk_dir = Path(env_dir)
    else:
        xdg_data = os.environ.get("XDG_DATA_HOME")
        if xdg_data:
            _bulk_dir = Path(xdg_data) / "turi-safe-chem-db" / "pubchem-bulk"
        else:
            _bulk_dir = Path.home() / ".turi-safe-chem-db" / "pubchem-bulk"

    _bulk_dir.mkdir(parents=True, exist_ok=True)
    return _bulk_dir


def _is_bulk_disabled() -> bool:
    """Check if bulk lookup is disabled via environment."""
    global _bulk_disabled
    if _bulk_disabled is not None:
        return _bulk_disabled
    _bulk_disabled = os.environ.get("PUBCHEM_DISABLE_BULK", "").strip() == "1"
    return _bulk_disabled


def _get_index_db_path() -> Path:
    """Return path to the SQLite index database."""
    return _get_bulk_dir() / "pubchem_bulk_index.sqlite"


def _get_metadata_path() -> Path:
    """Return path to the metadata JSON file."""
    return _get_bulk_dir() / "metadata.json"


def _read_metadata() -> Dict[str, Any]:
    """Read metadata file if it exists."""
    path = _get_metadata_path()
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_metadata(data: Dict[str, Any]) -> None:
    """Write metadata file."""
    path = _get_metadata_path()
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _is_valid_cas(s: str) -> bool:
    """Check if string looks like a CAS number."""
    return bool(CAS_PATTERN.match(s))


def _stream_gzip_lines(path: Path) -> Iterator[str]:
    """Stream lines from a gzip file without loading entire file into memory."""
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            yield line.rstrip("\n\r")


def _download_file(url: str, dest: Path, progress_callback=None) -> bool:
    """Download a file with streaming, resumable downloads.

    Returns True on success, False on failure.
    """
    temp_path = dest.with_suffix(dest.suffix + ".tmp")

    for attempt in range(MAX_DOWNLOAD_RETRIES):
        try:
            headers = {}
            start_byte = 0

            if temp_path.is_file():
                start_byte = temp_path.stat().st_size
                headers["Range"] = f"bytes={start_byte}-"

            resp = requests.get(
                url, headers=headers, stream=True, timeout=REQUEST_TIMEOUT
            )

            if resp.status_code == 416:
                temp_path.unlink(missing_ok=True)
                continue

            if resp.status_code not in (200, 206):
                if attempt + 1 < MAX_DOWNLOAD_RETRIES:
                    time.sleep(2 ** attempt)
                    continue
                return False

            total_size = None
            content_range = resp.headers.get("Content-Range")
            if content_range and "/" in content_range:
                total_size = int(content_range.split("/")[-1])
            elif "Content-Length" in resp.headers:
                total_size = int(resp.headers["Content-Length"]) + start_byte

            mode = "ab" if start_byte > 0 else "wb"
            downloaded = start_byte

            with open(temp_path, mode) as f:
                for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback and total_size:
                            progress_callback(downloaded, total_size)

            temp_path.rename(dest)
            return True

        except requests.RequestException as e:
            if attempt + 1 < MAX_DOWNLOAD_RETRIES:
                time.sleep(2 ** attempt)
                continue
            print(f"Download failed after {MAX_DOWNLOAD_RETRIES} attempts: {e}")
            return False

    return False


def _get_remote_file_date(url: str) -> Optional[datetime]:
    """Get Last-Modified date from remote file via HEAD request."""
    try:
        resp = requests.head(url, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            last_mod = resp.headers.get("Last-Modified")
            if last_mod:
                from email.utils import parsedate_to_datetime
                return parsedate_to_datetime(last_mod)
    except Exception:
        pass
    return None


def _needs_refresh(file_key: str, metadata: Dict[str, Any]) -> bool:
    """Check if a bulk file needs refresh based on age."""
    file_meta = metadata.get("files", {}).get(file_key, {})
    last_downloaded = file_meta.get("downloaded_at")
    if not last_downloaded:
        return True

    try:
        last_dt = datetime.fromisoformat(last_downloaded)
        age_days = (datetime.now(timezone.utc) - last_dt).days
        return age_days >= REFRESH_INTERVAL_DAYS
    except Exception:
        return True


def _create_index_schema(conn: sqlite3.Connection) -> None:
    """Create SQLite index schema."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS cas_to_cid (
            cas TEXT PRIMARY KEY,
            cid INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS cid_data (
            cid INTEGER PRIMARY KEY,
            smiles TEXT,
            title TEXT,
            inchikey TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_cas_cid ON cas_to_cid(cid);
    """)


def _index_synonyms(conn: sqlite3.Connection, path: Path, progress_callback=None) -> int:
    """Index CAS → CID mappings from CID-Synonym-filtered.gz.

    File format: CID<tab>Synonym (one per line, many synonyms per CID)
    We only index synonyms that look like CAS numbers.

    Returns count of CAS entries indexed.
    """
    batch = []
    batch_size = 50000
    count = 0
    line_num = 0

    for line in _stream_gzip_lines(path):
        line_num += 1
        if not line or "\t" not in line:
            continue

        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue

        try:
            cid = int(parts[0])
        except ValueError:
            continue

        synonym = parts[1].strip()
        if not _is_valid_cas(synonym):
            continue

        batch.append((synonym, cid))
        count += 1

        if len(batch) >= batch_size:
            conn.executemany(
                "INSERT OR REPLACE INTO cas_to_cid (cas, cid) VALUES (?, ?)",
                batch,
            )
            conn.commit()
            batch.clear()
            if progress_callback:
                progress_callback(f"CAS entries: {count:,}")

    if batch:
        conn.executemany(
            "INSERT OR REPLACE INTO cas_to_cid (cas, cid) VALUES (?, ?)",
            batch,
        )
        conn.commit()

    return count


def _index_smiles(conn: sqlite3.Connection, path: Path, progress_callback=None) -> int:
    """Index CID → SMILES from CID-SMILES.gz.

    File format: CID<tab>SMILES (one per line)
    """
    batch = []
    batch_size = 50000
    count = 0

    for line in _stream_gzip_lines(path):
        if not line or "\t" not in line:
            continue

        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue

        try:
            cid = int(parts[0])
        except ValueError:
            continue

        smiles = parts[1].strip()
        if not smiles:
            continue

        batch.append((cid, smiles))
        count += 1

        if len(batch) >= batch_size:
            conn.executemany(
                """INSERT INTO cid_data (cid, smiles) VALUES (?, ?)
                   ON CONFLICT(cid) DO UPDATE SET smiles = excluded.smiles""",
                batch,
            )
            conn.commit()
            batch.clear()
            if progress_callback:
                progress_callback(f"SMILES entries: {count:,}")

    if batch:
        conn.executemany(
            """INSERT INTO cid_data (cid, smiles) VALUES (?, ?)
               ON CONFLICT(cid) DO UPDATE SET smiles = excluded.smiles""",
            batch,
        )
        conn.commit()

    return count


def _index_titles(conn: sqlite3.Connection, path: Path, progress_callback=None) -> int:
    """Index CID → Title from CID-Title.gz.

    File format: CID<tab>Title (one per line)
    """
    batch = []
    batch_size = 50000
    count = 0

    for line in _stream_gzip_lines(path):
        if not line or "\t" not in line:
            continue

        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue

        try:
            cid = int(parts[0])
        except ValueError:
            continue

        title = parts[1].strip()
        if not title:
            continue

        batch.append((cid, title))
        count += 1

        if len(batch) >= batch_size:
            conn.executemany(
                """INSERT INTO cid_data (cid, title) VALUES (?, ?)
                   ON CONFLICT(cid) DO UPDATE SET title = excluded.title""",
                batch,
            )
            conn.commit()
            batch.clear()
            if progress_callback:
                progress_callback(f"Title entries: {count:,}")

    if batch:
        conn.executemany(
            """INSERT INTO cid_data (cid, title) VALUES (?, ?)
               ON CONFLICT(cid) DO UPDATE SET title = excluded.title""",
            batch,
        )
        conn.commit()

    return count


def _index_inchikeys(conn: sqlite3.Connection, path: Path, progress_callback=None) -> int:
    """Index CID → InChI Key from CID-InChI-Key.gz.

    File format: CID<tab>InChIKey (one per line)
    """
    batch = []
    batch_size = 50000
    count = 0

    for line in _stream_gzip_lines(path):
        if not line or "\t" not in line:
            continue

        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue

        try:
            cid = int(parts[0])
        except ValueError:
            continue

        inchikey = parts[1].strip()
        if not inchikey:
            continue

        batch.append((cid, inchikey))
        count += 1

        if len(batch) >= batch_size:
            conn.executemany(
                """INSERT INTO cid_data (cid, inchikey) VALUES (?, ?)
                   ON CONFLICT(cid) DO UPDATE SET inchikey = excluded.inchikey""",
                batch,
            )
            conn.commit()
            batch.clear()
            if progress_callback:
                progress_callback(f"InChI entries: {count:,}")

    if batch:
        conn.executemany(
            """INSERT INTO cid_data (cid, inchikey) VALUES (?, ?)
               ON CONFLICT(cid) DO UPDATE SET inchikey = excluded.inchikey""",
            batch,
        )
        conn.commit()

    return count


def build_index(force: bool = False, verbose: bool = True) -> Dict[str, Any]:
    """Download bulk files and build local index.

    Args:
        force: Force re-download even if files exist
        verbose: Print progress to stdout

    Returns:
        Dict with build statistics
    """
    bulk_dir = _get_bulk_dir()
    metadata = _read_metadata()
    stats: Dict[str, Any] = {"downloaded": [], "indexed": {}, "errors": []}

    def log(msg: str) -> None:
        if verbose:
            print(msg)

    log(f"Bulk data directory: {bulk_dir}")

    for file_key, filename in BULK_FILES.items():
        url = f"{PUBCHEM_FTP_BASE}/{filename}"
        local_path = bulk_dir / filename

        need_download = force or not local_path.is_file()

        if not need_download and not force:
            need_download = _needs_refresh(file_key, metadata)

        if need_download:
            log(f"Downloading {filename}...")

            def progress(downloaded, total):
                pct = (downloaded / total) * 100 if total else 0
                print(f"\r  {downloaded:,} / {total:,} bytes ({pct:.1f}%)", end="", flush=True)

            success = _download_file(url, local_path, progress_callback=progress if verbose else None)
            if verbose:
                print()

            if success:
                stats["downloaded"].append(filename)
                if "files" not in metadata:
                    metadata["files"] = {}
                metadata["files"][file_key] = {
                    "filename": filename,
                    "downloaded_at": datetime.now(timezone.utc).isoformat(),
                    "size_bytes": local_path.stat().st_size,
                }
            else:
                stats["errors"].append(f"Failed to download {filename}")
                log(f"  ERROR: Failed to download {filename}")
                continue
        else:
            log(f"Using existing {filename}")

    _write_metadata(metadata)

    log("\nBuilding SQLite index...")
    db_path = _get_index_db_path()

    if db_path.is_file() and force:
        db_path.unlink()

    conn = sqlite3.connect(str(db_path))
    try:
        _create_index_schema(conn)

        syn_path = bulk_dir / BULK_FILES["synonyms"]
        if syn_path.is_file():
            log("  Indexing CAS → CID mappings...")
            count = _index_synonyms(
                conn, syn_path,
                progress_callback=log if verbose else None
            )
            stats["indexed"]["cas_to_cid"] = count
            log(f"  Indexed {count:,} CAS entries")

        smiles_path = bulk_dir / BULK_FILES["smiles"]
        if smiles_path.is_file():
            log("  Indexing SMILES...")
            count = _index_smiles(
                conn, smiles_path,
                progress_callback=log if verbose else None
            )
            stats["indexed"]["smiles"] = count
            log(f"  Indexed {count:,} SMILES entries")

        title_path = bulk_dir / BULK_FILES["title"]
        if title_path.is_file():
            log("  Indexing titles...")
            count = _index_titles(
                conn, title_path,
                progress_callback=log if verbose else None
            )
            stats["indexed"]["titles"] = count
            log(f"  Indexed {count:,} title entries")

        inchi_path = bulk_dir / BULK_FILES["inchikey"]
        if inchi_path.is_file():
            log("  Indexing InChI keys...")
            count = _index_inchikeys(
                conn, inchi_path,
                progress_callback=log if verbose else None
            )
            stats["indexed"]["inchikeys"] = count
            log(f"  Indexed {count:,} InChI key entries")

        metadata["index_built_at"] = datetime.now(timezone.utc).isoformat()
        metadata["index_stats"] = stats["indexed"]
        _write_metadata(metadata)

    finally:
        conn.close()

    stats["db_path"] = str(db_path)
    stats["db_size_bytes"] = db_path.stat().st_size if db_path.is_file() else 0

    log(f"\nIndex built: {db_path}")
    log(f"Database size: {stats['db_size_bytes'] / (1024*1024):.1f} MB")

    return stats


def refresh_index(verbose: bool = True) -> Dict[str, Any]:
    """Check and update index if stale (>30 days old).

    Returns:
        Dict with refresh statistics
    """
    metadata = _read_metadata()
    needs_refresh_any = False

    for file_key in BULK_FILES:
        if _needs_refresh(file_key, metadata):
            needs_refresh_any = True
            break

    if needs_refresh_any:
        if verbose:
            print("Index is stale (>30 days), refreshing...")
        return build_index(force=True, verbose=verbose)
    else:
        if verbose:
            print("Index is up to date (refreshed within 30 days)")
        return {"status": "up_to_date", "metadata": metadata}


def get_index_status() -> Dict[str, Any]:
    """Get current index status and statistics."""
    bulk_dir = _get_bulk_dir()
    metadata = _read_metadata()
    db_path = _get_index_db_path()

    status: Dict[str, Any] = {
        "bulk_dir": str(bulk_dir),
        "db_exists": db_path.is_file(),
        "db_path": str(db_path),
        "bulk_disabled": _is_bulk_disabled(),
    }

    if db_path.is_file():
        status["db_size_bytes"] = db_path.stat().st_size
        status["db_size_mb"] = round(db_path.stat().st_size / (1024 * 1024), 1)

        try:
            conn = sqlite3.connect(str(db_path))
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM cas_to_cid")
            status["cas_count"] = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM cid_data")
            status["cid_count"] = cur.fetchone()[0]
            conn.close()
        except Exception as e:
            status["db_error"] = str(e)

    status["files"] = {}
    for file_key, filename in BULK_FILES.items():
        file_path = bulk_dir / filename
        file_status = {
            "exists": file_path.is_file(),
            "filename": filename,
        }
        if file_path.is_file():
            file_status["size_bytes"] = file_path.stat().st_size
            file_status["size_mb"] = round(file_path.stat().st_size / (1024 * 1024), 1)

        file_meta = metadata.get("files", {}).get(file_key, {})
        if file_meta.get("downloaded_at"):
            file_status["downloaded_at"] = file_meta["downloaded_at"]
            file_status["needs_refresh"] = _needs_refresh(file_key, metadata)

        status["files"][file_key] = file_status

    if metadata.get("index_built_at"):
        status["index_built_at"] = metadata["index_built_at"]
    if metadata.get("index_stats"):
        status["index_stats"] = metadata["index_stats"]

    return status


def lookup_cid_by_cas(cas: str) -> Optional[int]:
    """Look up CID by CAS number from local bulk index.

    Args:
        cas: CAS registry number (e.g., "67-64-1")

    Returns:
        CID if found in bulk index, None otherwise
    """
    if _is_bulk_disabled():
        return None

    db_path = _get_index_db_path()
    if not db_path.is_file():
        return None

    try:
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        cur.execute("SELECT cid FROM cas_to_cid WHERE cas = ?", (cas,))
        row = cur.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None


def lookup_cid_data(cid: int) -> Optional[Dict[str, Any]]:
    """Look up compound data by CID from local bulk index.

    Args:
        cid: PubChem compound ID

    Returns:
        Dict with smiles, title, inchikey if found, None otherwise
    """
    if _is_bulk_disabled():
        return None

    db_path = _get_index_db_path()
    if not db_path.is_file():
        return None

    try:
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        cur.execute(
            "SELECT smiles, title, inchikey FROM cid_data WHERE cid = ?",
            (cid,)
        )
        row = cur.fetchone()
        conn.close()

        if row:
            return {
                "smiles": row[0],
                "title": row[1],
                "inchikey": row[2],
            }
        return None
    except Exception:
        return None


def lookup_cas_full(cas: str) -> Optional[Dict[str, Any]]:
    """Look up full compound info by CAS from local bulk index.

    Combines CAS → CID lookup with CID data lookup.

    Args:
        cas: CAS registry number

    Returns:
        Dict with cid, smiles, title, inchikey if found, None otherwise
    """
    cid = lookup_cid_by_cas(cas)
    if cid is None:
        return None

    data = lookup_cid_data(cid)
    if data is None:
        return {"cid": cid}

    return {"cid": cid, **data}


def clear_bulk_data() -> Dict[str, Any]:
    """Remove all bulk data files and index.

    Returns:
        Dict with deletion statistics
    """
    bulk_dir = _get_bulk_dir()
    stats = {"deleted_files": [], "errors": []}

    for file_key, filename in BULK_FILES.items():
        path = bulk_dir / filename
        if path.is_file():
            try:
                path.unlink()
                stats["deleted_files"].append(filename)
            except Exception as e:
                stats["errors"].append(f"{filename}: {e}")

    db_path = _get_index_db_path()
    if db_path.is_file():
        try:
            db_path.unlink()
            stats["deleted_files"].append(db_path.name)
        except Exception as e:
            stats["errors"].append(f"{db_path.name}: {e}")

    meta_path = _get_metadata_path()
    if meta_path.is_file():
        try:
            meta_path.unlink()
            stats["deleted_files"].append(meta_path.name)
        except Exception as e:
            stats["errors"].append(f"{meta_path.name}: {e}")

    return stats


def main() -> int:
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="PubChem bulk index management for local CAS lookups"
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    build_parser = subparsers.add_parser("build", help="Download and build index")
    build_parser.add_argument(
        "--force", "-f", action="store_true",
        help="Force re-download even if files exist"
    )

    refresh_parser = subparsers.add_parser("refresh", help="Check and update if stale")

    status_parser = subparsers.add_parser("status", help="Show index status")
    status_parser.add_argument(
        "--json", action="store_true",
        help="Output as JSON"
    )

    clear_parser = subparsers.add_parser("clear", help="Remove all bulk data")
    clear_parser.add_argument(
        "--yes", "-y", action="store_true",
        help="Skip confirmation"
    )

    lookup_parser = subparsers.add_parser("lookup", help="Look up a CAS number")
    lookup_parser.add_argument("cas", help="CAS registry number")

    args = parser.parse_args()

    if args.command == "build":
        try:
            stats = build_index(force=args.force)
            if stats.get("errors"):
                print(f"\nWarnings/errors: {stats['errors']}")
                return 1
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1

    elif args.command == "refresh":
        try:
            stats = refresh_index()
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1

    elif args.command == "status":
        status = get_index_status()
        if args.json:
            print(json.dumps(status, indent=2))
        else:
            print(f"Bulk data directory: {status['bulk_dir']}")
            print(f"Bulk lookup disabled: {status['bulk_disabled']}")
            print(f"Database exists: {status['db_exists']}")
            if status['db_exists']:
                print(f"Database size: {status.get('db_size_mb', '?')} MB")
                print(f"CAS entries: {status.get('cas_count', '?'):,}")
                print(f"CID entries: {status.get('cid_count', '?'):,}")
            if status.get('index_built_at'):
                print(f"Index built: {status['index_built_at']}")
            print("\nBulk files:")
            for key, info in status['files'].items():
                exists = "✓" if info['exists'] else "✗"
                size = f"{info.get('size_mb', '?')} MB" if info['exists'] else "N/A"
                refresh = " (needs refresh)" if info.get('needs_refresh') else ""
                print(f"  {exists} {info['filename']}: {size}{refresh}")
        return 0

    elif args.command == "clear":
        if not args.yes:
            confirm = input("Delete all bulk data? [y/N] ").strip().lower()
            if confirm != "y":
                print("Aborted")
                return 1
        stats = clear_bulk_data()
        print(f"Deleted: {stats['deleted_files']}")
        if stats['errors']:
            print(f"Errors: {stats['errors']}")
            return 1
        return 0

    elif args.command == "lookup":
        result = lookup_cas_full(args.cas)
        if result:
            print(json.dumps(result, indent=2))
            return 0
        else:
            print(f"Not found in bulk index: {args.cas}")
            return 1

    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
