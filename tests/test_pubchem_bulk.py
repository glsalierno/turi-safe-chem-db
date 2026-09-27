"""Unit tests for PubChem bulk index functionality.

These tests use fixture files — NO live network calls.
"""

from __future__ import annotations

import gzip
import json
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from packages.doss_core import pubchem_bulk


@pytest.fixture
def temp_bulk_dir(monkeypatch):
    """Create a temporary bulk data directory for tests."""
    tmpdir = tempfile.mkdtemp(prefix="pubchem_bulk_test_")
    monkeypatch.setenv("PUBCHEM_BULK_DIR", tmpdir)
    monkeypatch.setenv("PUBCHEM_DISABLE_BULK", "0")
    pubchem_bulk._bulk_dir = None
    pubchem_bulk._bulk_disabled = None
    yield tmpdir
    shutil.rmtree(tmpdir, ignore_errors=True)
    pubchem_bulk._bulk_dir = None
    pubchem_bulk._bulk_disabled = None


@pytest.fixture
def fixture_synonyms_gz(temp_bulk_dir):
    """Create a small CID-Synonym-filtered.gz fixture file."""
    content = """\
180\t67-64-1
180\tAcetone
180\t2-Propanone
702\t64-17-5
702\tEthanol
702\tEthyl alcohol
6212\t7782-50-5
6212\tChlorine
887\t56-81-5
887\tGlycerol
5462309\t50-00-0
5462309\tFormaldehyde
5988\t64-19-7
5988\tAcetic acid
2723872\t75-09-2
2723872\tDichloromethane
2723872\tMethylene chloride
3007\t110-54-3
3007\tHexane
6569\t108-88-3
6569\tToluene
7501\t71-36-3
7501\t1-Butanol
"""
    path = Path(temp_bulk_dir) / "CID-Synonym-filtered.gz"
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write(content)
    return path


@pytest.fixture
def fixture_smiles_gz(temp_bulk_dir):
    """Create a small CID-SMILES.gz fixture file."""
    content = """\
180\tCC(=O)C
702\tCCO
6212\tClCl
887\tOCC(O)CO
5462309\tC=O
5988\tCC(=O)O
2723872\tClCCl
3007\tCCCCCC
6569\tCc1ccccc1
7501\tCCCCO
"""
    path = Path(temp_bulk_dir) / "CID-SMILES.gz"
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write(content)
    return path


@pytest.fixture
def fixture_title_gz(temp_bulk_dir):
    """Create a small CID-Title.gz fixture file."""
    content = """\
180\tAcetone
702\tEthanol
6212\tMolecular chlorine
887\tGlycerol
5462309\tFormaldehyde
5988\tAcetic acid
2723872\tDichloromethane
3007\tHexane
6569\tToluene
7501\t1-Butanol
"""
    path = Path(temp_bulk_dir) / "CID-Title.gz"
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write(content)
    return path


@pytest.fixture
def fixture_inchikey_gz(temp_bulk_dir):
    """Create a small CID-InChI-Key.gz fixture file."""
    content = """\
180\tCZCUKWEASQGHGC-UHFFFAOYSA-N
702\tLFQSCWFLJHTTHZ-UHFFFAOYSA-N
6212\tKZBUYRJHBYPTAX-UHFFFAOYSA-N
887\tPEDCQBHIVMGVHV-UHFFFAOYSA-N
5462309\tWSFSFENUMNVMXJ-UHFFFAOYSA-N
5988\tQTBSBXVTEAMEQO-UHFFFAOYSA-N
2723872\tYMWUJEATGCHEWI-UHFFFAOYSA-N
3007\tVLKZOEOYAKHREP-UHFFFAOYSA-N
6569\tYXFVVABEGXRONW-UHFFFAOYSA-N
7501\tLRHPLDYGYMQFCJ-UHFFFAOYSA-N
"""
    path = Path(temp_bulk_dir) / "CID-InChI-Key.gz"
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write(content)
    return path


@pytest.fixture
def all_fixtures(fixture_synonyms_gz, fixture_smiles_gz, fixture_title_gz, fixture_inchikey_gz):
    """Bundle all fixture files."""
    return {
        "synonyms": fixture_synonyms_gz,
        "smiles": fixture_smiles_gz,
        "title": fixture_title_gz,
        "inchikey": fixture_inchikey_gz,
    }


class TestBulkDirConfiguration:
    """Test bulk directory configuration."""

    def test_default_bulk_dir_xdg(self, monkeypatch, tmp_path):
        """Test XDG_DATA_HOME configuration."""
        xdg_dir = tmp_path / "xdg_data"
        monkeypatch.setenv("XDG_DATA_HOME", str(xdg_dir))
        monkeypatch.delenv("PUBCHEM_BULK_DIR", raising=False)
        pubchem_bulk._bulk_dir = None

        bulk_dir = pubchem_bulk._get_bulk_dir()
        assert "turi-safe-chem-db" in str(bulk_dir)
        assert "pubchem-bulk" in str(bulk_dir)

    def test_custom_bulk_dir_env(self, monkeypatch, tmp_path):
        """Test PUBCHEM_BULK_DIR environment variable."""
        custom_dir = tmp_path / "custom_bulk"
        monkeypatch.setenv("PUBCHEM_BULK_DIR", str(custom_dir))
        pubchem_bulk._bulk_dir = None

        bulk_dir = pubchem_bulk._get_bulk_dir()
        assert str(bulk_dir) == str(custom_dir)
        assert bulk_dir.exists()

    def test_bulk_disabled_env(self, monkeypatch):
        """Test PUBCHEM_DISABLE_BULK environment variable."""
        monkeypatch.setenv("PUBCHEM_DISABLE_BULK", "1")
        pubchem_bulk._bulk_disabled = None

        assert pubchem_bulk._is_bulk_disabled() is True

    def test_bulk_enabled_by_default(self, monkeypatch):
        """Test bulk is enabled by default."""
        monkeypatch.delenv("PUBCHEM_DISABLE_BULK", raising=False)
        pubchem_bulk._bulk_disabled = None

        assert pubchem_bulk._is_bulk_disabled() is False


class TestCasValidation:
    """Test CAS number validation."""

    def test_valid_cas_numbers(self):
        """Test recognition of valid CAS numbers."""
        valid_cases = [
            "67-64-1",    # Acetone
            "64-17-5",    # Ethanol
            "7782-50-5",  # Chlorine
            "50-00-0",    # Formaldehyde
            "1-23-4",     # Minimal
            "1234567-89-0",  # Max length
        ]
        for cas in valid_cases:
            assert pubchem_bulk._is_valid_cas(cas), f"{cas} should be valid"

    def test_invalid_cas_numbers(self):
        """Test rejection of invalid CAS numbers."""
        invalid_cases = [
            "Acetone",
            "C2H5OH",
            "123456789-12-3",  # Too long
            "12345-123-1",    # Wrong middle segment
            "12345-12-12",    # Wrong check digit length
            "",
            "abc-de-f",
        ]
        for cas in invalid_cases:
            assert not pubchem_bulk._is_valid_cas(cas), f"{cas} should be invalid"


class TestStreamingParser:
    """Test streaming parser doesn't load entire file into memory."""

    def test_stream_gzip_lines_yields_lines(self, fixture_synonyms_gz):
        """Test streaming yields individual lines."""
        lines = list(pubchem_bulk._stream_gzip_lines(fixture_synonyms_gz))
        assert len(lines) > 0
        assert all(isinstance(line, str) for line in lines)
        assert "180\t67-64-1" in lines

    def test_stream_gzip_lines_memory_bounded(self, temp_bulk_dir):
        """Test streaming doesn't load entire file — uses generator."""
        path = Path(temp_bulk_dir) / "large_test.gz"
        line_count = 100000

        with gzip.open(path, "wt", encoding="utf-8") as f:
            for i in range(line_count):
                f.write(f"{i}\tSynonym-{i}\n")

        gen = pubchem_bulk._stream_gzip_lines(path)
        assert hasattr(gen, "__iter__")
        assert hasattr(gen, "__next__")

        first_line = next(gen)
        assert first_line == "0\tSynonym-0"

        count = 1
        for _ in gen:
            count += 1
        assert count == line_count


class TestIndexBuilding:
    """Test index building from fixture files."""

    def test_index_synonyms(self, temp_bulk_dir, fixture_synonyms_gz):
        """Test CAS → CID indexing."""
        db_path = Path(temp_bulk_dir) / "test_index.sqlite"
        conn = sqlite3.connect(str(db_path))
        pubchem_bulk._create_index_schema(conn)

        count = pubchem_bulk._index_synonyms(conn, fixture_synonyms_gz)

        assert count > 0

        cur = conn.cursor()
        cur.execute("SELECT cid FROM cas_to_cid WHERE cas = ?", ("67-64-1",))
        row = cur.fetchone()
        assert row is not None
        assert row[0] == 180

        cur.execute("SELECT cid FROM cas_to_cid WHERE cas = ?", ("64-17-5",))
        row = cur.fetchone()
        assert row is not None
        assert row[0] == 702

        conn.close()

    def test_index_smiles(self, temp_bulk_dir, fixture_smiles_gz):
        """Test CID → SMILES indexing."""
        db_path = Path(temp_bulk_dir) / "test_index.sqlite"
        conn = sqlite3.connect(str(db_path))
        pubchem_bulk._create_index_schema(conn)

        count = pubchem_bulk._index_smiles(conn, fixture_smiles_gz)

        assert count > 0

        cur = conn.cursor()
        cur.execute("SELECT smiles FROM cid_data WHERE cid = ?", (180,))
        row = cur.fetchone()
        assert row is not None
        assert row[0] == "CC(=O)C"

        conn.close()

    def test_index_titles(self, temp_bulk_dir, fixture_title_gz):
        """Test CID → Title indexing."""
        db_path = Path(temp_bulk_dir) / "test_index.sqlite"
        conn = sqlite3.connect(str(db_path))
        pubchem_bulk._create_index_schema(conn)

        count = pubchem_bulk._index_titles(conn, fixture_title_gz)

        assert count > 0

        cur = conn.cursor()
        cur.execute("SELECT title FROM cid_data WHERE cid = ?", (180,))
        row = cur.fetchone()
        assert row is not None
        assert row[0] == "Acetone"

        conn.close()

    def test_index_inchikeys(self, temp_bulk_dir, fixture_inchikey_gz):
        """Test CID → InChI key indexing."""
        db_path = Path(temp_bulk_dir) / "test_index.sqlite"
        conn = sqlite3.connect(str(db_path))
        pubchem_bulk._create_index_schema(conn)

        count = pubchem_bulk._index_inchikeys(conn, fixture_inchikey_gz)

        assert count > 0

        cur = conn.cursor()
        cur.execute("SELECT inchikey FROM cid_data WHERE cid = ?", (180,))
        row = cur.fetchone()
        assert row is not None
        assert "CZCUKWEASQGHGC" in row[0]

        conn.close()


class TestLookups:
    """Test lookup functions with indexed data."""

    @pytest.fixture
    def indexed_db(self, temp_bulk_dir, all_fixtures):
        """Build a complete index from fixtures."""
        db_path = pubchem_bulk._get_index_db_path()
        conn = sqlite3.connect(str(db_path))
        pubchem_bulk._create_index_schema(conn)

        pubchem_bulk._index_synonyms(conn, all_fixtures["synonyms"])
        pubchem_bulk._index_smiles(conn, all_fixtures["smiles"])
        pubchem_bulk._index_titles(conn, all_fixtures["title"])
        pubchem_bulk._index_inchikeys(conn, all_fixtures["inchikey"])

        conn.close()
        return db_path

    def test_lookup_cid_by_cas_found(self, indexed_db):
        """Test CAS → CID lookup when CAS exists."""
        cid = pubchem_bulk.lookup_cid_by_cas("67-64-1")
        assert cid == 180

        cid = pubchem_bulk.lookup_cid_by_cas("64-17-5")
        assert cid == 702

    def test_lookup_cid_by_cas_not_found(self, indexed_db):
        """Test CAS → CID lookup when CAS doesn't exist."""
        cid = pubchem_bulk.lookup_cid_by_cas("99999-99-9")
        assert cid is None

    def test_lookup_cid_data_found(self, indexed_db):
        """Test CID → data lookup when CID exists."""
        data = pubchem_bulk.lookup_cid_data(180)
        assert data is not None
        assert data["smiles"] == "CC(=O)C"
        assert data["title"] == "Acetone"
        assert "CZCUKWEASQGHGC" in data["inchikey"]

    def test_lookup_cid_data_not_found(self, indexed_db):
        """Test CID → data lookup when CID doesn't exist."""
        data = pubchem_bulk.lookup_cid_data(999999999)
        assert data is None

    def test_lookup_cas_full(self, indexed_db):
        """Test combined CAS lookup."""
        data = pubchem_bulk.lookup_cas_full("67-64-1")
        assert data is not None
        assert data["cid"] == 180
        assert data["smiles"] == "CC(=O)C"
        assert data["title"] == "Acetone"

    def test_lookup_cas_full_not_found(self, indexed_db):
        """Test combined CAS lookup when not found."""
        data = pubchem_bulk.lookup_cas_full("99999-99-9")
        assert data is None

    def test_lookup_disabled_returns_none(self, indexed_db, monkeypatch):
        """Test lookups return None when bulk is disabled."""
        monkeypatch.setenv("PUBCHEM_DISABLE_BULK", "1")
        pubchem_bulk._bulk_disabled = None

        assert pubchem_bulk.lookup_cid_by_cas("67-64-1") is None
        assert pubchem_bulk.lookup_cid_data(180) is None


class TestFallbackIntegration:
    """Test integration with pubchem.py fallback behavior."""

    @pytest.fixture
    def indexed_db(self, temp_bulk_dir, all_fixtures):
        """Build a complete index from fixtures."""
        db_path = pubchem_bulk._get_index_db_path()
        conn = sqlite3.connect(str(db_path))
        pubchem_bulk._create_index_schema(conn)
        pubchem_bulk._index_synonyms(conn, all_fixtures["synonyms"])
        pubchem_bulk._index_smiles(conn, all_fixtures["smiles"])
        conn.close()
        return db_path

    def test_pubchem_get_cid_uses_bulk_first(self, indexed_db, monkeypatch):
        """Test get_cid_by_cas uses bulk index first."""
        from packages.doss_core import pubchem

        monkeypatch.setenv("PUBCHEM_CACHE_DIR", str(Path(indexed_db).parent / "api_cache"))
        pubchem._CACHE_DIR = None

        with mock.patch("requests.get") as mock_get:
            cid = pubchem.get_cid_by_cas("67-64-1")
            mock_get.assert_not_called()
            assert cid == 180

    def test_pubchem_falls_back_to_api_on_miss(self, indexed_db, monkeypatch):
        """Test get_cid_by_cas falls back to API on bulk miss."""
        from packages.doss_core import pubchem

        cache_dir = Path(indexed_db).parent / "api_cache"
        monkeypatch.setenv("PUBCHEM_CACHE_DIR", str(cache_dir))
        monkeypatch.setenv("PUBCHEM_MIN_INTERVAL_S", "0.01")
        pubchem._CACHE_DIR = None
        pubchem._MIN_INTERVAL_S = 0.01

        mock_resp = mock.Mock()
        mock_resp.status_code = 200
        mock_resp.headers = {}
        mock_resp.json.return_value = {"IdentifierList": {"CID": [12345]}}
        mock_resp.raise_for_status = mock.Mock()

        with mock.patch("requests.get", return_value=mock_resp) as mock_get:
            cid = pubchem.get_cid_by_cas("99999-99-9")
            mock_get.assert_called_once()
            assert cid == 12345


class TestIndexStatus:
    """Test index status reporting."""

    def test_status_no_index(self, temp_bulk_dir):
        """Test status when no index exists."""
        status = pubchem_bulk.get_index_status()
        assert status["db_exists"] is False
        assert "bulk_dir" in status

    def test_status_with_index(self, temp_bulk_dir, all_fixtures):
        """Test status after building index."""
        db_path = pubchem_bulk._get_index_db_path()
        conn = sqlite3.connect(str(db_path))
        pubchem_bulk._create_index_schema(conn)
        pubchem_bulk._index_synonyms(conn, all_fixtures["synonyms"])
        conn.close()

        status = pubchem_bulk.get_index_status()
        assert status["db_exists"] is True
        assert status["cas_count"] > 0


class TestMetadata:
    """Test metadata file handling."""

    def test_read_missing_metadata(self, temp_bulk_dir):
        """Test reading non-existent metadata returns empty dict."""
        meta = pubchem_bulk._read_metadata()
        assert meta == {}

    def test_write_and_read_metadata(self, temp_bulk_dir):
        """Test writing and reading metadata."""
        data = {"test_key": "test_value", "number": 42}
        pubchem_bulk._write_metadata(data)

        meta = pubchem_bulk._read_metadata()
        assert meta["test_key"] == "test_value"
        assert meta["number"] == 42


class TestClearBulkData:
    """Test clearing bulk data."""

    def test_clear_removes_files(self, temp_bulk_dir, all_fixtures):
        """Test clear removes all bulk files."""
        db_path = pubchem_bulk._get_index_db_path()
        conn = sqlite3.connect(str(db_path))
        pubchem_bulk._create_index_schema(conn)
        conn.close()

        pubchem_bulk._write_metadata({"test": True})

        stats = pubchem_bulk.clear_bulk_data()

        assert len(stats["deleted_files"]) > 0
        assert not db_path.is_file()
        assert not pubchem_bulk._get_metadata_path().is_file()
