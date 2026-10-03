"""
IUCLID endpoint cache: SQLite storage for extracted endpoints.

Provides:
- IUCLIDCache class for reading/writing cached endpoints
- CLI for building cache from dossiers:
    python -m packages.iuclid_core.cache build --scope universe
    python -m packages.iuclid_core.cache build --cas-list file.txt
    python -m packages.iuclid_core.cache build --all
    python -m packages.iuclid_core.cache status
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Iterator

logger = logging.getLogger(__name__)

EXTRACTOR_VERSION = "1.0.0"

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS endpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cas TEXT NOT NULL,
    uuid TEXT NOT NULL,
    subtype TEXT NOT NULL,
    endpoint_json TEXT NOT NULL,
    extractor_version TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_endpoints_cas ON endpoints(cas);
CREATE INDEX IF NOT EXISTS idx_endpoints_uuid ON endpoints(uuid);
CREATE INDEX IF NOT EXISTS idx_endpoints_subtype ON endpoints(subtype);

CREATE TABLE IF NOT EXISTS processed_uuids (
    uuid TEXT PRIMARY KEY,
    cas TEXT,
    endpoint_count INTEGER,
    extractor_version TEXT,
    processed_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


class IUCLIDCache:
    """
    SQLite cache for extracted IUCLID endpoints.
    
    Stores endpoints keyed by CAS and UUID for fast lookup.
    """
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._ensure_schema()
    
    def _ensure_schema(self) -> None:
        """Create tables if they don't exist."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        try:
            conn.executescript(SCHEMA)
            conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                ("schema_version", "1"),
            )
            conn.commit()
        finally:
            conn.close()
    
    def get_endpoints_for_cas(self, cas: str) -> list[dict]:
        """Get all cached endpoints for a CAS number."""
        from packages.iuclid_core.index import normalize_cas
        cas = normalize_cas(cas)
        
        conn = sqlite3.connect(self.db_path)
        try:
            results = []
            for (endpoint_json,) in conn.execute(
                "SELECT endpoint_json FROM endpoints WHERE cas = ?", (cas,)
            ):
                try:
                    results.append(json.loads(endpoint_json))
                except json.JSONDecodeError:
                    pass
            return results
        finally:
            conn.close()
    
    def get_endpoints_for_uuid(self, uuid: str) -> list[dict]:
        """Get all cached endpoints for a dossier UUID."""
        conn = sqlite3.connect(self.db_path)
        try:
            results = []
            for (endpoint_json,) in conn.execute(
                "SELECT endpoint_json FROM endpoints WHERE uuid = ?", (uuid,)
            ):
                try:
                    results.append(json.loads(endpoint_json))
                except json.JSONDecodeError:
                    pass
            return results
        finally:
            conn.close()
    
    def is_uuid_processed(
        self, uuid: str, version: str = EXTRACTOR_VERSION
    ) -> bool:
        """Check if a UUID has been processed with current extractor version."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                "SELECT 1 FROM processed_uuids WHERE uuid = ? AND extractor_version = ?",
                (uuid, version),
            )
            return cursor.fetchone() is not None
        finally:
            conn.close()
    
    def store_endpoints(
        self,
        cas: str,
        uuid: str,
        endpoints: list[dict],
    ) -> int:
        """
        Store extracted endpoints for a CAS/UUID pair.
        
        Returns number of endpoints stored.
        """
        from packages.iuclid_core.index import normalize_cas
        cas = normalize_cas(cas)
        
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "DELETE FROM endpoints WHERE uuid = ?", (uuid,)
            )
            
            for ep in endpoints:
                subtype = ep.get("subtype", "unknown")
                conn.execute(
                    """
                    INSERT INTO endpoints (cas, uuid, subtype, endpoint_json, extractor_version)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (cas, uuid, subtype, json.dumps(ep), EXTRACTOR_VERSION),
                )
            
            conn.execute(
                """
                INSERT OR REPLACE INTO processed_uuids 
                (uuid, cas, endpoint_count, extractor_version)
                VALUES (?, ?, ?, ?)
                """,
                (uuid, cas, len(endpoints), EXTRACTOR_VERSION),
            )
            
            conn.commit()
            return len(endpoints)
        finally:
            conn.close()
    
    def get_status(self) -> dict[str, Any]:
        """Get cache status information."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute("SELECT COUNT(*) FROM endpoints")
            endpoint_count = cursor.fetchone()[0]
            
            cursor = conn.execute("SELECT COUNT(*) FROM processed_uuids")
            uuid_count = cursor.fetchone()[0]
            
            cursor = conn.execute("SELECT COUNT(DISTINCT cas) FROM endpoints")
            cas_count = cursor.fetchone()[0]
            
            cursor = conn.execute(
                "SELECT value FROM meta WHERE key = 'schema_version'"
            )
            row = cursor.fetchone()
            schema_version = row[0] if row else "unknown"
            
            return {
                "db_path": str(self.db_path),
                "endpoint_count": endpoint_count,
                "uuid_count": uuid_count,
                "cas_count": cas_count,
                "schema_version": schema_version,
                "extractor_version": EXTRACTOR_VERSION,
            }
        finally:
            conn.close()
    
    def clear(self) -> None:
        """Clear all cached data."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("DELETE FROM endpoints")
            conn.execute("DELETE FROM processed_uuids")
            conn.commit()
        finally:
            conn.close()


_cache_instance: IUCLIDCache | None = None


def get_cache() -> IUCLIDCache | None:
    """Get the configured cache instance."""
    global _cache_instance
    
    if _cache_instance is not None:
        return _cache_instance
    
    from packages.iuclid_core.config import get_config
    config = get_config()
    
    if not config.enabled:
        return None
    
    db_path = config.cache_dir / "iuclid_endpoints.db"
    _cache_instance = IUCLIDCache(db_path)
    return _cache_instance


def reset_cache() -> None:
    """Reset cached cache instance (for testing)."""
    global _cache_instance
    _cache_instance = None


def iter_cas_from_file(cas_file: Path) -> Iterator[str]:
    """Iterate CAS numbers from a text file (one per line)."""
    from packages.iuclid_core.index import normalize_cas
    
    with open(cas_file, encoding="utf-8") as f:
        for line in f:
            cas = line.strip()
            if cas and not cas.startswith("#"):
                norm = normalize_cas(cas)
                if norm:
                    yield norm


def iter_universe_cas() -> Iterator[str]:
    """Iterate CAS numbers from the P2OASys universe (~1255 CAS)."""
    from packages.iuclid_core.index import normalize_cas
    
    universe_paths = [
        Path("data/priority_cas_list.txt"),
        Path("data/p2oasys_score_lookup.sqlite"),
    ]
    
    for path in universe_paths:
        if path.exists():
            if path.suffix == ".txt":
                yield from iter_cas_from_file(path)
                return
            elif path.suffix == ".sqlite":
                conn = sqlite3.connect(path)
                try:
                    for (cas,) in conn.execute(
                        "SELECT DISTINCT cas FROM p2oasys_scores"
                    ):
                        norm = normalize_cas(cas)
                        if norm:
                            yield norm
                finally:
                    conn.close()
                return
    
    logger.warning("No universe CAS list found")


def iter_all_indexed_cas() -> Iterator[str]:
    """Iterate all CAS numbers from the configured index."""
    from packages.iuclid_core.index import load_index
    
    index = load_index()
    yield from index.keys()


def build_cache_for_cas_list(
    cas_iter: Iterator[str],
    cache: IUCLIDCache | None = None,
    skip_processed: bool = True,
    progress_callback: Any = None,
) -> dict[str, int]:
    """
    Build cache by extracting endpoints for a list of CAS numbers.
    
    Args:
        cas_iter: Iterator of CAS numbers
        cache: Cache instance (defaults to global)
        skip_processed: Skip UUIDs already processed with current version
        progress_callback: Optional callback(cas, uuid, count) for progress
    
    Returns:
        Dict with stats: processed_cas, processed_uuids, total_endpoints
    """
    from packages.iuclid_core.index import (
        get_dossier_uuids_for_cas,
        get_dossier_path,
    )
    from packages.iuclid_core.extractor import extract_dossier
    from packages.iuclid_core.phrase_mapper import get_phrase_mapper
    
    if cache is None:
        cache = get_cache()
        if cache is None:
            logger.error("Cache not available - check IUCLID configuration")
            return {"processed_cas": 0, "processed_uuids": 0, "total_endpoints": 0}
    
    phrases = get_phrase_mapper()
    
    stats = {
        "processed_cas": 0,
        "processed_uuids": 0,
        "total_endpoints": 0,
        "skipped_uuids": 0,
        "failed_uuids": 0,
    }
    
    processed_cas_set: set[str] = set()
    
    for cas in cas_iter:
        if cas in processed_cas_set:
            continue
        processed_cas_set.add(cas)
        
        uuids = get_dossier_uuids_for_cas(cas)
        if not uuids:
            logger.debug("No dossiers for CAS: %s", cas)
            continue
        
        for uuid in uuids:
            if skip_processed and cache.is_uuid_processed(uuid):
                stats["skipped_uuids"] += 1
                continue
            
            dossier_path = get_dossier_path(uuid)
            if dossier_path is None:
                logger.debug("Dossier not found: %s", uuid)
                stats["failed_uuids"] += 1
                continue
            
            try:
                records = extract_dossier(dossier_path, uuid, phrases)
                endpoints = [r.to_dict() for r in records]
                count = cache.store_endpoints(cas, uuid, endpoints)
                
                stats["processed_uuids"] += 1
                stats["total_endpoints"] += count
                
                if progress_callback:
                    progress_callback(cas, uuid, count)
                
                logger.debug(
                    "Extracted %d endpoints from %s (%s)", count, uuid, cas
                )
            except Exception as e:
                logger.warning("Failed to process %s: %s", uuid, e)
                stats["failed_uuids"] += 1
        
        stats["processed_cas"] += 1
    
    return stats


def main() -> None:
    """CLI entry point."""
    import argparse
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )
    
    parser = argparse.ArgumentParser(
        prog="python -m packages.iuclid_core.cache",
        description="IUCLID endpoint cache management",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    build_parser = subparsers.add_parser("build", help="Build cache from dossiers")
    build_group = build_parser.add_mutually_exclusive_group(required=True)
    build_group.add_argument(
        "--scope",
        choices=["universe"],
        help="Build for predefined scope (universe = P2OASys ~1255 CAS)",
    )
    build_group.add_argument(
        "--cas-list",
        type=Path,
        help="Build for CAS numbers in file (one per line)",
    )
    build_group.add_argument(
        "--all",
        action="store_true",
        help="Build for all CAS numbers in index",
    )
    build_parser.add_argument(
        "--force",
        action="store_true",
        help="Re-process even if already cached",
    )
    build_parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output",
    )
    
    status_parser = subparsers.add_parser("status", help="Show cache status")
    
    clear_parser = subparsers.add_parser("clear", help="Clear cache")
    clear_parser.add_argument(
        "--confirm",
        action="store_true",
        required=True,
        help="Confirm cache clear",
    )
    
    args = parser.parse_args()
    
    if args.command == "status":
        cache = get_cache()
        if cache is None:
            print("IUCLID not configured")
            from packages.iuclid_core.config import get_status
            status = get_status()
            print(f"  Reason: {status.get('disable_reason', 'unknown')}")
            sys.exit(1)
        
        status = cache.get_status()
        print("IUCLID Cache Status:")
        print(f"  Database: {status['db_path']}")
        print(f"  Endpoints: {status['endpoint_count']:,}")
        print(f"  Dossiers: {status['uuid_count']:,}")
        print(f"  CAS numbers: {status['cas_count']:,}")
        print(f"  Extractor version: {status['extractor_version']}")
        return
    
    if args.command == "clear":
        cache = get_cache()
        if cache is None:
            print("IUCLID not configured")
            sys.exit(1)
        cache.clear()
        print("Cache cleared")
        return
    
    if args.command == "build":
        if args.verbose:
            logging.getLogger("packages.iuclid_core").setLevel(logging.DEBUG)
        
        cache = get_cache()
        if cache is None:
            print("IUCLID not configured - cannot build cache")
            from packages.iuclid_core.config import get_status
            status = get_status()
            print(f"  Reason: {status.get('disable_reason', 'unknown')}")
            sys.exit(1)
        
        if args.scope == "universe":
            print("Building cache for P2OASys universe...")
            cas_iter = iter_universe_cas()
        elif args.cas_list:
            print(f"Building cache from {args.cas_list}...")
            cas_iter = iter_cas_from_file(args.cas_list)
        elif args.all:
            print("Building cache for all indexed CAS numbers...")
            cas_iter = iter_all_indexed_cas()
        else:
            parser.error("No scope specified")
            return
        
        def progress(cas: str, uuid: str, count: int) -> None:
            print(f"  {cas}: {uuid} -> {count} endpoints")
        
        stats = build_cache_for_cas_list(
            cas_iter,
            cache,
            skip_processed=not args.force,
            progress_callback=progress if args.verbose else None,
        )
        
        print(f"\nBuild complete:")
        print(f"  CAS numbers: {stats['processed_cas']:,}")
        print(f"  Dossiers processed: {stats['processed_uuids']:,}")
        print(f"  Dossiers skipped: {stats['skipped_uuids']:,}")
        print(f"  Dossiers failed: {stats['failed_uuids']:,}")
        print(f"  Total endpoints: {stats['total_endpoints']:,}")


if __name__ == "__main__":
    main()
