"""
SDS cache lookup - read-only offline lookup for pre-downloaded SDS PDFs.

Cache layout: DIR/<cas>/<vendor>/<revision>/<sha256[:12]>/original.pdf
Optionally with metadata.json and parsed.json alongside.

The real GHaz7 cache mixes CAS folder spellings (both "109999" and "115-86-6").
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from packages.capability_config import SDSEnrichConfig


def get_cache_dir() -> Path | None:
    """Get SDS cache directory from config."""
    try:
        cache_path = SDSEnrichConfig.sds_cache_dir()
        if cache_path and cache_path.exists():
            return cache_path
    except Exception:
        pass
    return None


def _parse_date(date_str: str) -> datetime | None:
    """Parse date from various formats."""
    if not date_str:
        return None
    
    for fmt in (
        "%m/%d/%Y",
        "%m_%d_%Y",
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%Y/%m/%d",
    ):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    m = re.match(r"(\d{1,2})[_/](\d{1,2})[_/](\d{4})", date_str)
    if m:
        try:
            month, day, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
            return datetime(year, month, day)
        except ValueError:
            pass
    
    return None


def _get_revision_date(pdf_dir: Path) -> datetime | None:
    """Get revision date from metadata.json or folder name."""
    metadata_path = pdf_dir / "metadata.json"
    if metadata_path.exists():
        try:
            with open(metadata_path, encoding="utf-8") as f:
                meta = json.load(f)
            
            if meta.get("revision"):
                date = _parse_date(meta["revision"])
                if date:
                    return date
            
            if meta.get("stored_at"):
                date = _parse_date(meta["stored_at"])
                if date:
                    return date
        except Exception:
            pass
    
    revision_folder = pdf_dir.parent.name
    date = _parse_date(revision_folder)
    if date:
        return date
    
    return None


def _sha256_file(path: Path) -> str:
    """Compute SHA256 hash of file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def lookup_sds_in_cache(
    cas: str,
    cache_dir: Path | None = None,
) -> dict[str, any] | None:
    """
    Look up SDS PDF in cache for a CAS number.
    
    Tries both dashed and digits-only CAS folder names.
    Picks the newest revision deterministically.
    
    Args:
        cas: CAS registry number
        cache_dir: Override cache directory (defaults to config)
    
    Returns:
        Dict with keys: path, vendor, revision, sha256, relative_path, candidates
        or None if not found
    """
    if cache_dir is None:
        cache_dir = get_cache_dir()
    
    if cache_dir is None or not cache_dir.exists():
        return None
    
    cas_normalized = cas.replace("-", "")
    cas_dashed = cas
    
    candidates: list[dict] = []
    
    for cas_folder in (cas_dashed, cas_normalized):
        cas_path = cache_dir / cas_folder
        if not cas_path.exists():
            continue
        
        for pdf_path in cas_path.glob("*/**/original.pdf"):
            try:
                pdf_dir = pdf_path.parent
                parts = pdf_path.relative_to(cas_path).parts
                
                vendor = parts[0] if len(parts) > 1 else "unknown"
                
                revision_date = _get_revision_date(pdf_dir)
                
                mtime = datetime.fromtimestamp(pdf_path.stat().st_mtime)
                
                sha256 = _sha256_file(pdf_path)
                
                candidates.append({
                    "path": pdf_path,
                    "vendor": vendor,
                    "revision_date": revision_date,
                    "mtime": mtime,
                    "sha256": sha256,
                    "relative_path": str(pdf_path.relative_to(cache_dir)),
                })
            except Exception:
                continue
    
    if not candidates:
        return None
    
    def sort_key(c: dict):
        return (
            c["revision_date"] or datetime.min,
            c["mtime"] or datetime.min,
            c["relative_path"],
        )
    
    candidates.sort(key=sort_key, reverse=True)
    
    best = candidates[0]
    
    revision_str = ""
    if best["revision_date"]:
        revision_str = best["revision_date"].strftime("%Y-%m-%d")
    
    return {
        "path": best["path"],
        "vendor": best["vendor"],
        "revision": revision_str,
        "sha256": best["sha256"],
        "relative_path": best["relative_path"],
        "candidates": [
            {
                "path": str(c["path"]),
                "vendor": c["vendor"],
                "revision": c["revision_date"].strftime("%Y-%m-%d") if c["revision_date"] else "",
            }
            for c in candidates
        ],
    }
