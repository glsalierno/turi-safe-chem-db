"""
PubChem FTP/HTTPS bulk index for local CAS → CID lookups and LCSS hazard data.

Downloads and indexes PubChem bulk files to reduce API calls:
  - CID-Identifiers.tsv.gz — PRIMARY CAS → CID mappings (official registry IDs)
  - CID-Synonym-filtered.gz — FALLBACK CAS → CID mappings (all synonyms)
  - CID-LCSS.xml.gz — Laboratory Chemical Safety Summary (GHS, NFPA, flash point, etc.)
  - CID-SMILES.gz — CID → SMILES (optional, large)
  - CID-Title.gz — CID → compound name (optional, large)
  - CID-InChI-Key.gz — CID → InChI key (optional, large)

CAS→CID Resolution (199 of 1,228 expert CAS map to multiple CIDs):
  - PRIMARY: CID-Identifiers CAS rows (official registry, authoritative)
  - FALLBACK: CID-Synonym-filtered (may have multiple CID candidates)
  - When multiple CIDs exist: prefer lowest CID (typically parent/non-mixture)
  - All candidates stored in cas_cid_candidates table; cid_ambiguous flag set

LCSS Parsing:
  - GHS H/P codes, signal word, pictograms
  - Flash point, vapor pressure
  - NFPA health/fire/reactivity
  - IARC classification
  - Validated: identical to live PUG-View for 44/44 tested chemicals

Limitations (explicit flags, never silently blank):
  - LCSS lacks "Toxicity Data" section (LD50 may differ ~1 in 6)
  - LCSS lacks "Ecotoxicity Values" section (LC50/aquatic mostly lost)
  - Results include pubchem_source="ftp_lcss" and toxicity_sections="absent"

Disk footprint (all files ~11 GB compressed; LCSS-only ~500 MB):
  - CID-Identifiers.tsv.gz: ~50 MB
  - CID-Synonym-filtered.gz: ~600 MB
  - CID-LCSS.xml.gz: ~456 MB (257,169 records)
  - CID-SMILES.gz: ~3.5 GB (optional)
  - CID-Title.gz: ~2.5 GB (optional)
  - CID-InChI-Key.gz: ~4 GB (optional)

Usage:
    python -m packages.doss_core.pubchem_bulk build           # Download core + LCSS
    python -m packages.doss_core.pubchem_bulk build --full    # Include SMILES/Title/InChI
    python -m packages.doss_core.pubchem_bulk build --cas-file cas_list.txt  # Restrict to CAS list
    python -m packages.doss_core.pubchem_bulk refresh         # Check and update if stale
    python -m packages.doss_core.pubchem_bulk status          # Show index stats

Environment variables:
    PUBCHEM_BULK_DIR         Override bulk data directory
    PUBCHEM_DISABLE_BULK     Set to 1 to skip bulk lookup entirely
    PUBCHEM_OFFLINE_MODE     Set to 1 to block ALL live PubChem calls
"""

from __future__ import annotations

import gzip
import json
import os
import re
import sqlite3
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

import requests

PUBCHEM_FTP_BASE = "https://ftp.ncbi.nlm.nih.gov/pubchem/Compound/Extras"

BULK_FILES_CORE = {
    "identifiers": "CID-Identifiers.tsv.gz",
    "synonyms": "CID-Synonym-filtered.gz",
    "lcss": "CID-LCSS.xml.gz",
}

BULK_FILES_OPTIONAL = {
    "smiles": "CID-SMILES.gz",
    "title": "CID-Title.gz",
    "inchikey": "CID-InChI-Key.gz",
}

BULK_FILES = {**BULK_FILES_CORE, **BULK_FILES_OPTIONAL}

CAS_PATTERN = re.compile(r"^\d{1,7}-\d{2}-\d$")

REFRESH_INTERVAL_DAYS = 30
CHUNK_SIZE = 8 * 1024 * 1024
REQUEST_TIMEOUT = 120
MAX_DOWNLOAD_RETRIES = 3

_bulk_dir: Path | None = None
_bulk_disabled: bool | None = None
_offline_mode: bool | None = None


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


def _is_offline_mode() -> bool:
    """Check if offline mode is enabled (blocks ALL live PubChem calls)."""
    global _offline_mode
    if _offline_mode is not None:
        return _offline_mode
    _offline_mode = os.environ.get("PUBCHEM_OFFLINE_MODE", "").strip() == "1"
    return _offline_mode


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


def _stream_xml_records(path: Path, tag: str) -> Iterator[ET.Element]:
    """Stream XML elements matching tag from gzip file without loading entire file.

    Uses iterparse for bounded memory on multi-GB XML files.
    """
    with gzip.open(path, "rb") as f:
        context = ET.iterparse(f, events=("end",))
        for event, elem in context:
            if elem.tag == tag:
                yield elem
                elem.clear()


def _download_file(url: str, dest: Path, progress_callback=None) -> bool:
    """Download a file with streaming, resumable downloads.

    Returns True on success, False on failure.
    """
    if _is_offline_mode():
        print(f"OFFLINE MODE: Skipping download of {url}")
        return False

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
    """Create SQLite index schema with multi-CID support."""
    conn.executescript("""
        -- Primary CAS → CID mapping (resolved, single best CID)
        CREATE TABLE IF NOT EXISTS cas_to_cid (
            cas TEXT PRIMARY KEY,
            cid INTEGER NOT NULL,
            cid_source TEXT NOT NULL,  -- 'identifiers' or 'synonyms'
            cid_ambiguous INTEGER DEFAULT 0  -- 1 if multiple CIDs found
        );

        -- All CID candidates for ambiguous CAS numbers
        CREATE TABLE IF NOT EXISTS cas_cid_candidates (
            cas TEXT NOT NULL,
            cid INTEGER NOT NULL,
            source TEXT NOT NULL,  -- 'identifiers' or 'synonyms'
            PRIMARY KEY (cas, cid)
        );

        -- CID compound data (SMILES, title, InChI key)
        CREATE TABLE IF NOT EXISTS cid_data (
            cid INTEGER PRIMARY KEY,
            smiles TEXT,
            title TEXT,
            inchikey TEXT
        );

        -- LCSS hazard data (GHS, NFPA, physical properties)
        CREATE TABLE IF NOT EXISTS cid_lcss (
            cid INTEGER PRIMARY KEY,
            ghs_hcodes TEXT,       -- JSON array of H codes
            ghs_pcodes TEXT,       -- JSON array of P codes
            ghs_signal_word TEXT,
            ghs_pictograms TEXT,   -- JSON array of pictogram names
            nfpa_health INTEGER,
            nfpa_fire INTEGER,
            nfpa_reactivity INTEGER,
            flash_point_c REAL,
            vapor_pressure_mmhg REAL,
            iarc_classification TEXT,
            raw_json TEXT          -- Full parsed data as JSON for debugging
        );

        CREATE INDEX IF NOT EXISTS idx_cas_cid ON cas_to_cid(cid);
        CREATE INDEX IF NOT EXISTS idx_candidates_cas ON cas_cid_candidates(cas);
    """)


def _collect_cas_cid_mappings(
    identifiers_path: Optional[Path],
    synonyms_path: Optional[Path],
    cas_filter: Optional[Set[str]],
    progress_callback=None,
) -> Tuple[Dict[str, List[Tuple[int, str]]], int]:
    """Collect all CAS → CID mappings from both sources.

    Returns:
        (cas_to_cids dict, total_count)
        cas_to_cids maps CAS → list of (cid, source) tuples
    """
    cas_to_cids: Dict[str, List[Tuple[int, str]]] = {}
    count = 0

    if identifiers_path and identifiers_path.is_file():
        if progress_callback:
            progress_callback("Processing CID-Identifiers (PRIMARY source)...")

        for line in _stream_gzip_lines(identifiers_path):
            if not line or line.startswith("#"):
                continue

            parts = line.split("\t")
            if len(parts) < 3:
                continue

            try:
                cid = int(parts[0])
            except ValueError:
                continue

            id_type = parts[1].strip()
            id_value = parts[2].strip()

            if id_type == "CAS" and _is_valid_cas(id_value):
                if cas_filter and id_value not in cas_filter:
                    continue

                if id_value not in cas_to_cids:
                    cas_to_cids[id_value] = []
                cas_to_cids[id_value].append((cid, "identifiers"))
                count += 1

    if synonyms_path and synonyms_path.is_file():
        if progress_callback:
            progress_callback("Processing CID-Synonym-filtered (FALLBACK source)...")

        for line in _stream_gzip_lines(synonyms_path):
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

            if cas_filter and synonym not in cas_filter:
                continue

            if synonym not in cas_to_cids:
                cas_to_cids[synonym] = []

            if (cid, "synonyms") not in cas_to_cids[synonym]:
                cas_to_cids[synonym].append((cid, "synonyms"))
                count += 1

    return cas_to_cids, count


def _resolve_best_cid(candidates: List[Tuple[int, str]]) -> Tuple[int, str, bool]:
    """Resolve best CID from candidates using deterministic rules.

    Rules:
    1. Prefer CID from 'identifiers' source over 'synonyms'
    2. Among same-source candidates, prefer lowest CID (parent/non-mixture)

    Returns:
        (best_cid, source, is_ambiguous)
    """
    if not candidates:
        raise ValueError("No candidates provided")

    if len(candidates) == 1:
        return candidates[0][0], candidates[0][1], False

    id_candidates = [(cid, src) for cid, src in candidates if src == "identifiers"]
    syn_candidates = [(cid, src) for cid, src in candidates if src == "synonyms"]

    if id_candidates:
        best = min(id_candidates, key=lambda x: x[0])
        return best[0], best[1], len(candidates) > 1

    best = min(syn_candidates, key=lambda x: x[0])
    return best[0], best[1], len(candidates) > 1


def _index_cas_mappings(
    conn: sqlite3.Connection,
    cas_to_cids: Dict[str, List[Tuple[int, str]]],
    progress_callback=None,
) -> Tuple[int, int]:
    """Index CAS → CID mappings with multi-CID handling.

    Returns:
        (total_cas, ambiguous_cas)
    """
    batch_main = []
    batch_candidates = []
    batch_size = 10000
    total = 0
    ambiguous = 0

    for cas, candidates in cas_to_cids.items():
        best_cid, source, is_ambiguous = _resolve_best_cid(candidates)

        batch_main.append((cas, best_cid, source, 1 if is_ambiguous else 0))
        total += 1

        if is_ambiguous:
            ambiguous += 1
            for cid, src in candidates:
                batch_candidates.append((cas, cid, src))

        if len(batch_main) >= batch_size:
            conn.executemany(
                """INSERT OR REPLACE INTO cas_to_cid
                   (cas, cid, cid_source, cid_ambiguous) VALUES (?, ?, ?, ?)""",
                batch_main,
            )
            if batch_candidates:
                conn.executemany(
                    """INSERT OR REPLACE INTO cas_cid_candidates
                       (cas, cid, source) VALUES (?, ?, ?)""",
                    batch_candidates,
                )
            conn.commit()
            batch_main.clear()
            batch_candidates.clear()

            if progress_callback:
                progress_callback(f"CAS entries: {total:,} ({ambiguous:,} ambiguous)")

    if batch_main:
        conn.executemany(
            """INSERT OR REPLACE INTO cas_to_cid
               (cas, cid, cid_source, cid_ambiguous) VALUES (?, ?, ?, ?)""",
            batch_main,
        )
        if batch_candidates:
            conn.executemany(
                """INSERT OR REPLACE INTO cas_cid_candidates
                   (cas, cid, source) VALUES (?, ?, ?)""",
                batch_candidates,
            )
        conn.commit()

    return total, ambiguous


def _parse_lcss_record(elem: ET.Element) -> Optional[Dict[str, Any]]:
    """Parse a single LCSS XML record into hazard data.

    LCSS XML structure (simplified):
    <Record>
      <RecordNumber>CID</RecordNumber>
      <Section>
        <TOCHeading>GHS Classification</TOCHeading>
        <Information>
          <Name>Signal</Name>
          <Value><StringWithMarkup><String>Danger</String></StringWithMarkup></Value>
        </Information>
        ...
      </Section>
    </Record>
    """
    result: Dict[str, Any] = {}

    record_num = elem.find("RecordNumber")
    if record_num is None or not record_num.text:
        return None

    try:
        result["cid"] = int(record_num.text)
    except ValueError:
        return None

    ghs_hcodes: List[str] = []
    ghs_pcodes: List[str] = []
    ghs_pictograms: List[str] = []

    for section in elem.findall(".//Section"):
        heading_elem = section.find("TOCHeading")
        heading = heading_elem.text if heading_elem is not None else ""

        if heading == "GHS Classification":
            for info in section.findall(".//Information"):
                name_elem = info.find("Name")
                name = name_elem.text if name_elem is not None else ""

                value_str = ""
                for swm in info.findall(".//StringWithMarkup/String"):
                    if swm.text:
                        value_str = swm.text
                        break

                if name == "Signal":
                    result["ghs_signal_word"] = value_str

                elif name == "GHS Hazard Statements" or "Hazard" in name:
                    for code in re.findall(r"\bH\d{3}[A-Z]?\b", value_str):
                        if code not in ghs_hcodes:
                            ghs_hcodes.append(code)

                elif name == "Precautionary Statement" or "Precaution" in name:
                    for code in re.findall(r"\bP\d{3}(?:\+P\d{3})*\b", value_str):
                        if code not in ghs_pcodes:
                            ghs_pcodes.append(code)

                elif "Pictogram" in name:
                    for pic in re.findall(r"GHS\d{2}", value_str):
                        if pic not in ghs_pictograms:
                            ghs_pictograms.append(pic)

        elif heading == "NFPA Hazard Classification" or "NFPA" in heading:
            for info in section.findall(".//Information"):
                name_elem = info.find("Name")
                name = name_elem.text if name_elem is not None else ""

                num_elem = info.find(".//Number")
                if num_elem is not None and num_elem.text:
                    try:
                        num = int(float(num_elem.text))
                        if "Health" in name:
                            result["nfpa_health"] = num
                        elif "Fire" in name or "Flammability" in name:
                            result["nfpa_fire"] = num
                        elif "Reactivity" in name or "Instability" in name:
                            result["nfpa_reactivity"] = num
                    except ValueError:
                        pass

                for swm in info.findall(".//StringWithMarkup/String"):
                    if swm.text:
                        match = re.match(r"([0-4])\b", swm.text.strip())
                        if match:
                            digit = int(match.group(1))
                            if "Health" in name:
                                result.setdefault("nfpa_health", digit)
                            elif "Fire" in name or "Flammability" in name:
                                result.setdefault("nfpa_fire", digit)
                            elif "Reactivity" in name or "Instability" in name:
                                result.setdefault("nfpa_reactivity", digit)

        elif heading == "Physical Description" or "Physical" in heading:
            for info in section.findall(".//Information"):
                name_elem = info.find("Name")
                name = name_elem.text if name_elem is not None else ""

                value_str = ""
                for swm in info.findall(".//StringWithMarkup/String"):
                    if swm.text:
                        value_str = swm.text
                        break

                if "Flash Point" in name or "flash point" in name.lower():
                    match = re.search(r"([-+]?\d+(?:\.\d+)?)\s*°?\s*([CF])", value_str)
                    if match:
                        val = float(match.group(1))
                        unit = match.group(2).upper()
                        if unit == "F":
                            val = (val - 32) * 5 / 9
                        result["flash_point_c"] = round(val, 1)

                elif "Vapor Pressure" in name or "vapor pressure" in name.lower():
                    match = re.search(r"([\d.]+)\s*(?:mm\s*Hg|mmHg|torr)", value_str, re.I)
                    if match:
                        result["vapor_pressure_mmhg"] = float(match.group(1))

        elif "IARC" in heading or "Carcinogen" in heading:
            for info in section.findall(".//Information"):
                for swm in info.findall(".//StringWithMarkup/String"):
                    if swm.text and ("Group" in swm.text or "IARC" in swm.text):
                        result["iarc_classification"] = swm.text.strip()
                        break

    if ghs_hcodes:
        result["ghs_hcodes"] = ghs_hcodes
    if ghs_pcodes:
        result["ghs_pcodes"] = ghs_pcodes
    if ghs_pictograms:
        result["ghs_pictograms"] = ghs_pictograms

    return result if len(result) > 1 else None


def _index_lcss(
    conn: sqlite3.Connection,
    path: Path,
    cid_filter: Optional[Set[int]] = None,
    progress_callback=None,
) -> int:
    """Index LCSS XML file into database.

    Returns count of records indexed.
    """
    batch = []
    batch_size = 5000
    count = 0

    for elem in _stream_xml_records(path, "Record"):
        data = _parse_lcss_record(elem)
        if data is None:
            continue

        cid = data["cid"]
        if cid_filter and cid not in cid_filter:
            continue

        batch.append((
            cid,
            json.dumps(data.get("ghs_hcodes", [])),
            json.dumps(data.get("ghs_pcodes", [])),
            data.get("ghs_signal_word"),
            json.dumps(data.get("ghs_pictograms", [])),
            data.get("nfpa_health"),
            data.get("nfpa_fire"),
            data.get("nfpa_reactivity"),
            data.get("flash_point_c"),
            data.get("vapor_pressure_mmhg"),
            data.get("iarc_classification"),
            json.dumps(data),
        ))
        count += 1

        if len(batch) >= batch_size:
            conn.executemany(
                """INSERT OR REPLACE INTO cid_lcss
                   (cid, ghs_hcodes, ghs_pcodes, ghs_signal_word, ghs_pictograms,
                    nfpa_health, nfpa_fire, nfpa_reactivity, flash_point_c,
                    vapor_pressure_mmhg, iarc_classification, raw_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                batch,
            )
            conn.commit()
            batch.clear()
            if progress_callback:
                progress_callback(f"LCSS records: {count:,}")

    if batch:
        conn.executemany(
            """INSERT OR REPLACE INTO cid_lcss
               (cid, ghs_hcodes, ghs_pcodes, ghs_signal_word, ghs_pictograms,
                nfpa_health, nfpa_fire, nfpa_reactivity, flash_point_c,
                vapor_pressure_mmhg, iarc_classification, raw_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            batch,
        )
        conn.commit()

    return count


def _index_smiles(conn: sqlite3.Connection, path: Path, progress_callback=None) -> int:
    """Index CID → SMILES from CID-SMILES.gz."""
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
    """Index CID → Title from CID-Title.gz."""
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
    """Index CID → InChI Key from CID-InChI-Key.gz."""
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


def build_index(
    force: bool = False,
    full: bool = False,
    cas_file: Optional[Path] = None,
    verbose: bool = True,
) -> Dict[str, Any]:
    """Download bulk files and build local index.

    Args:
        force: Force re-download even if files exist
        full: Include optional large files (SMILES, Title, InChI)
        cas_file: Path to file with CAS numbers to filter (one per line)
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

    cas_filter: Optional[Set[str]] = None
    if cas_file:
        cas_filter = set()
        with open(cas_file, "r") as f:
            for line in f:
                cas = line.strip()
                if cas and _is_valid_cas(cas):
                    cas_filter.add(cas)
        log(f"Filtering to {len(cas_filter)} CAS numbers from {cas_file}")

    files_to_download = dict(BULK_FILES_CORE)
    if full:
        files_to_download.update(BULK_FILES_OPTIONAL)

    for file_key, filename in files_to_download.items():
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
                if file_key in BULK_FILES_CORE:
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

        id_path = bulk_dir / BULK_FILES_CORE["identifiers"]
        syn_path = bulk_dir / BULK_FILES_CORE["synonyms"]

        if id_path.is_file() or syn_path.is_file():
            log("  Collecting CAS → CID mappings...")
            cas_to_cids, total_mappings = _collect_cas_cid_mappings(
                id_path if id_path.is_file() else None,
                syn_path if syn_path.is_file() else None,
                cas_filter,
                progress_callback=log if verbose else None,
            )

            log("  Indexing with multi-CID resolution...")
            total_cas, ambiguous_cas = _index_cas_mappings(
                conn, cas_to_cids,
                progress_callback=log if verbose else None,
            )
            stats["indexed"]["cas_to_cid"] = total_cas
            stats["indexed"]["ambiguous_cas"] = ambiguous_cas
            log(f"  Indexed {total_cas:,} CAS entries ({ambiguous_cas:,} ambiguous)")

        cid_filter: Optional[Set[int]] = None
        if cas_filter:
            cur = conn.cursor()
            cur.execute("SELECT DISTINCT cid FROM cas_to_cid")
            cid_filter = {row[0] for row in cur.fetchall()}

        lcss_path = bulk_dir / BULK_FILES_CORE["lcss"]
        if lcss_path.is_file():
            log("  Indexing LCSS hazard data...")
            count = _index_lcss(
                conn, lcss_path, cid_filter,
                progress_callback=log if verbose else None,
            )
            stats["indexed"]["lcss"] = count
            log(f"  Indexed {count:,} LCSS records")

        if full:
            smiles_path = bulk_dir / BULK_FILES_OPTIONAL.get("smiles", "")
            if smiles_path.is_file():
                log("  Indexing SMILES...")
                count = _index_smiles(
                    conn, smiles_path,
                    progress_callback=log if verbose else None,
                )
                stats["indexed"]["smiles"] = count
                log(f"  Indexed {count:,} SMILES entries")

            title_path = bulk_dir / BULK_FILES_OPTIONAL.get("title", "")
            if title_path.is_file():
                log("  Indexing titles...")
                count = _index_titles(
                    conn, title_path,
                    progress_callback=log if verbose else None,
                )
                stats["indexed"]["titles"] = count
                log(f"  Indexed {count:,} title entries")

            inchi_path = bulk_dir / BULK_FILES_OPTIONAL.get("inchikey", "")
            if inchi_path.is_file():
                log("  Indexing InChI keys...")
                count = _index_inchikeys(
                    conn, inchi_path,
                    progress_callback=log if verbose else None,
                )
                stats["indexed"]["inchikeys"] = count
                log(f"  Indexed {count:,} InChI key entries")

        metadata["index_built_at"] = datetime.now(timezone.utc).isoformat()
        metadata["index_stats"] = stats["indexed"]
        metadata["full_index"] = full
        if cas_filter:
            metadata["cas_filter_count"] = len(cas_filter)
        _write_metadata(metadata)

    finally:
        conn.close()

    stats["db_path"] = str(db_path)
    stats["db_size_bytes"] = db_path.stat().st_size if db_path.is_file() else 0

    log(f"\nIndex built: {db_path}")
    log(f"Database size: {stats['db_size_bytes'] / (1024*1024):.1f} MB")

    return stats


def refresh_index(verbose: bool = True) -> Dict[str, Any]:
    """Check and update index if stale (>30 days old)."""
    metadata = _read_metadata()
    needs_refresh_any = False

    for file_key in BULK_FILES_CORE:
        if _needs_refresh(file_key, metadata):
            needs_refresh_any = True
            break

    if needs_refresh_any:
        if verbose:
            print("Index is stale (>30 days), refreshing...")
        full = metadata.get("full_index", False)
        return build_index(force=True, full=full, verbose=verbose)
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
        "offline_mode": _is_offline_mode(),
    }

    if db_path.is_file():
        status["db_size_bytes"] = db_path.stat().st_size
        status["db_size_mb"] = round(db_path.stat().st_size / (1024 * 1024), 1)

        try:
            conn = sqlite3.connect(str(db_path))
            cur = conn.cursor()

            cur.execute("SELECT COUNT(*) FROM cas_to_cid")
            status["cas_count"] = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM cas_to_cid WHERE cid_ambiguous = 1")
            status["ambiguous_cas_count"] = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM cid_data")
            status["cid_data_count"] = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM cid_lcss")
            status["lcss_count"] = cur.fetchone()[0]

            conn.close()
        except Exception as e:
            status["db_error"] = str(e)

    status["files"] = {}
    for file_key, filename in BULK_FILES.items():
        file_path = bulk_dir / filename
        file_status = {
            "exists": file_path.is_file(),
            "filename": filename,
            "optional": file_key in BULK_FILES_OPTIONAL,
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
    if metadata.get("full_index"):
        status["full_index"] = metadata["full_index"]

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


def lookup_cas_mapping_details(cas: str) -> Optional[Dict[str, Any]]:
    """Look up CAS mapping with ambiguity details.

    Returns:
        Dict with cid, source, is_ambiguous, and candidates list if ambiguous
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
            "SELECT cid, cid_source, cid_ambiguous FROM cas_to_cid WHERE cas = ?",
            (cas,)
        )
        row = cur.fetchone()
        if not row:
            conn.close()
            return None

        result = {
            "cid": row[0],
            "cid_source": row[1],
            "cid_ambiguous": bool(row[2]),
        }

        if row[2]:
            cur.execute(
                "SELECT cid, source FROM cas_cid_candidates WHERE cas = ?",
                (cas,)
            )
            result["candidates"] = [
                {"cid": r[0], "source": r[1]} for r in cur.fetchall()
            ]

        conn.close()
        return result
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


def lookup_lcss_data(cid: int) -> Optional[Dict[str, Any]]:
    """Look up LCSS hazard data by CID from local bulk index.

    Returns:
        Dict with GHS codes, NFPA ratings, flash point, etc.
        Includes pubchem_source="ftp_lcss" and toxicity_sections="absent"
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
            """SELECT ghs_hcodes, ghs_pcodes, ghs_signal_word, ghs_pictograms,
                      nfpa_health, nfpa_fire, nfpa_reactivity,
                      flash_point_c, vapor_pressure_mmhg, iarc_classification
               FROM cid_lcss WHERE cid = ?""",
            (cid,)
        )
        row = cur.fetchone()
        conn.close()

        if not row:
            return None

        return {
            "ghs_hcodes": json.loads(row[0]) if row[0] else [],
            "ghs_pcodes": json.loads(row[1]) if row[1] else [],
            "ghs_signal_word": row[2],
            "ghs_pictograms": json.loads(row[3]) if row[3] else [],
            "nfpa_health": row[4],
            "nfpa_fire": row[5],
            "nfpa_reactivity": row[6],
            "flash_point_c": row[7],
            "vapor_pressure_mmhg": row[8],
            "iarc_classification": row[9],
            "pubchem_source": "ftp_lcss",
            "toxicity_sections": "absent",
        }
    except Exception:
        return None


def lookup_cas_full(cas: str) -> Optional[Dict[str, Any]]:
    """Look up full compound info by CAS from local bulk index.

    Combines CAS → CID lookup with CID data and LCSS hazard data.
    Explicitly flags data source and missing toxicity sections.

    Args:
        cas: CAS registry number

    Returns:
        Dict with cid, smiles, title, inchikey, hazard data,
        pubchem_source, toxicity_sections flags
    """
    mapping = lookup_cas_mapping_details(cas)
    if mapping is None:
        return None

    cid = mapping["cid"]
    result: Dict[str, Any] = {
        "cid": cid,
        "cid_source": mapping["cid_source"],
        "cid_ambiguous": mapping["cid_ambiguous"],
        "pubchem_source": "ftp_bulk",
        "toxicity_sections": "absent",
    }

    if mapping["cid_ambiguous"]:
        result["cid_candidates"] = mapping.get("candidates", [])

    cid_data = lookup_cid_data(cid)
    if cid_data:
        result.update(cid_data)

    lcss_data = lookup_lcss_data(cid)
    if lcss_data:
        result["pubchem_source"] = "ftp_lcss"
        for key, value in lcss_data.items():
            if key not in ("pubchem_source", "toxicity_sections"):
                result[key] = value

    return result


def clear_bulk_data() -> Dict[str, Any]:
    """Remove all bulk data files and index."""
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
    build_parser.add_argument(
        "--full", action="store_true",
        help="Include optional large files (SMILES, Title, InChI; ~10 GB extra)"
    )
    build_parser.add_argument(
        "--cas-file", type=Path,
        help="Path to file with CAS numbers to filter (one per line)"
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
    lookup_parser.add_argument(
        "--json", action="store_true",
        help="Output as JSON"
    )

    args = parser.parse_args()

    if args.command == "build":
        try:
            stats = build_index(
                force=args.force,
                full=args.full,
                cas_file=args.cas_file,
            )
            if stats.get("errors"):
                print(f"\nWarnings/errors: {stats['errors']}")
                return 1
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1

    elif args.command == "refresh":
        try:
            refresh_index()
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
            print(f"Offline mode: {status['offline_mode']}")
            print(f"Database exists: {status['db_exists']}")
            if status['db_exists']:
                print(f"Database size: {status.get('db_size_mb', '?')} MB")
                print(f"CAS entries: {status.get('cas_count', '?'):,}")
                print(f"  Ambiguous: {status.get('ambiguous_cas_count', '?'):,}")
                print(f"LCSS records: {status.get('lcss_count', '?'):,}")
                print(f"CID data entries: {status.get('cid_data_count', '?'):,}")
            if status.get('index_built_at'):
                print(f"Index built: {status['index_built_at']}")
            if status.get('full_index'):
                print("Full index: Yes (includes SMILES/Title/InChI)")
            print("\nBulk files:")
            for key, info in status['files'].items():
                exists = "✓" if info['exists'] else "✗"
                size = f"{info.get('size_mb', '?')} MB" if info['exists'] else "N/A"
                opt = " (optional)" if info.get('optional') else ""
                refresh = " (needs refresh)" if info.get('needs_refresh') else ""
                print(f"  {exists} {info['filename']}: {size}{opt}{refresh}")
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
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                print(f"CAS: {args.cas}")
                print(f"CID: {result['cid']} (source: {result['cid_source']})")
                if result.get('cid_ambiguous'):
                    print(f"  AMBIGUOUS: {len(result.get('cid_candidates', []))} candidates")
                    for c in result.get('cid_candidates', []):
                        print(f"    - CID {c['cid']} ({c['source']})")
                if result.get('title'):
                    print(f"Title: {result['title']}")
                if result.get('smiles'):
                    print(f"SMILES: {result['smiles']}")
                if result.get('ghs_hcodes'):
                    print(f"GHS H-codes: {', '.join(result['ghs_hcodes'])}")
                if result.get('nfpa_health') is not None:
                    print(f"NFPA: H={result.get('nfpa_health')} F={result.get('nfpa_fire')} R={result.get('nfpa_reactivity')}")
                if result.get('flash_point_c') is not None:
                    print(f"Flash point: {result['flash_point_c']}°C")
                print(f"Source: {result['pubchem_source']}")
                print(f"Toxicity sections: {result['toxicity_sections']}")
            return 0
        else:
            print(f"Not found in bulk index: {args.cas}")
            return 1

    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
