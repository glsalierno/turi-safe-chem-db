"""Unit tests for PubChem bulk index functionality.

These tests use synthetic fixture files — NO live network calls.

Tests cover:
  - CAS → CID mapping with multi-CID resolution
  - CID-Identifiers (PRIMARY) vs CID-Synonym-filtered (FALLBACK) priority
  - LCSS XML parsing for GHS, NFPA, flash point
  - Streaming parser memory bounds
  - Offline mode behavior
  - API fallback on bulk miss
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
    monkeypatch.setenv("PUBCHEM_OFFLINE_MODE", "0")
    pubchem_bulk._bulk_dir = None
    pubchem_bulk._bulk_disabled = None
    pubchem_bulk._offline_mode = None
    yield tmpdir
    shutil.rmtree(tmpdir, ignore_errors=True)
    pubchem_bulk._bulk_dir = None
    pubchem_bulk._bulk_disabled = None
    pubchem_bulk._offline_mode = None


@pytest.fixture
def fixture_identifiers_gz(temp_bulk_dir):
    """Create a small CID-Identifiers.tsv.gz fixture file (PRIMARY source).

    Format: CID<tab>ID_TYPE<tab>ID_VALUE
    """
    content = """\
# CID	ID_TYPE	ID_VALUE
180	CAS	67-64-1
702	CAS	64-17-5
6212	CAS	7782-50-5
887	CAS	56-81-5
5462309	CAS	50-00-0
5988	CAS	64-19-7
2723872	CAS	75-09-2
3007	CAS	110-54-3
6569	CAS	108-88-3
7501	CAS	71-36-3
"""
    path = Path(temp_bulk_dir) / "CID-Identifiers.tsv.gz"
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write(content)
    return path


@pytest.fixture
def fixture_synonyms_gz(temp_bulk_dir):
    """Create a small CID-Synonym-filtered.gz fixture file (FALLBACK source).

    This includes some CAS numbers that conflict with identifiers (multi-CID case).
    Format: CID<tab>Synonym
    """
    content = """\
180	67-64-1
180	Acetone
180	2-Propanone
702	64-17-5
702	Ethanol
702	Ethyl alcohol
6212	7782-50-5
6212	Chlorine
887	56-81-5
887	Glycerol
5462309	50-00-0
5462309	Formaldehyde
5988	64-19-7
5988	Acetic acid
2723872	75-09-2
2723872	Dichloromethane
2723872	Methylene chloride
3007	110-54-3
3007	Hexane
6569	108-88-3
6569	Toluene
7501	71-36-3
7501	1-Butanol
12345	67-64-1
99999	67-64-1
54321	64-17-5
"""
    path = Path(temp_bulk_dir) / "CID-Synonym-filtered.gz"
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write(content)
    return path


@pytest.fixture
def fixture_lcss_xml_gz(temp_bulk_dir):
    """Create a small CID-LCSS.xml.gz fixture file with GHS/NFPA data."""
    content = """\
<?xml version="1.0" encoding="UTF-8"?>
<Records>
  <Record>
    <RecordNumber>180</RecordNumber>
    <Section>
      <TOCHeading>GHS Classification</TOCHeading>
      <Information>
        <Name>Signal</Name>
        <Value><StringWithMarkup><String>Danger</String></StringWithMarkup></Value>
      </Information>
      <Information>
        <Name>GHS Hazard Statements</Name>
        <Value><StringWithMarkup><String>H225: Highly flammable liquid and vapor</String></StringWithMarkup></Value>
      </Information>
      <Information>
        <Name>GHS Hazard Statements</Name>
        <Value><StringWithMarkup><String>H319: Causes serious eye irritation</String></StringWithMarkup></Value>
      </Information>
      <Information>
        <Name>Pictogram</Name>
        <Value><StringWithMarkup><String>GHS02 GHS07</String></StringWithMarkup></Value>
      </Information>
    </Section>
    <Section>
      <TOCHeading>NFPA Hazard Classification</TOCHeading>
      <Information>
        <Name>NFPA Health Rating</Name>
        <Value><Number>1</Number></Value>
      </Information>
      <Information>
        <Name>NFPA Fire Rating</Name>
        <Value><Number>3</Number></Value>
      </Information>
      <Information>
        <Name>NFPA Reactivity Rating</Name>
        <Value><Number>0</Number></Value>
      </Information>
    </Section>
    <Section>
      <TOCHeading>Physical Description</TOCHeading>
      <Information>
        <Name>Flash Point</Name>
        <Value><StringWithMarkup><String>-20 °C (-4 °F)</String></StringWithMarkup></Value>
      </Information>
      <Information>
        <Name>Vapor Pressure</Name>
        <Value><StringWithMarkup><String>184 mmHg at 20 °C</String></StringWithMarkup></Value>
      </Information>
    </Section>
  </Record>
  <Record>
    <RecordNumber>702</RecordNumber>
    <Section>
      <TOCHeading>GHS Classification</TOCHeading>
      <Information>
        <Name>Signal</Name>
        <Value><StringWithMarkup><String>Danger</String></StringWithMarkup></Value>
      </Information>
      <Information>
        <Name>GHS Hazard Statements</Name>
        <Value><StringWithMarkup><String>H225: Highly flammable liquid and vapor</String></StringWithMarkup></Value>
      </Information>
    </Section>
    <Section>
      <TOCHeading>NFPA Hazard Classification</TOCHeading>
      <Information>
        <Name>NFPA Health Rating</Name>
        <Value><StringWithMarkup><String>0 - Normal material</String></StringWithMarkup></Value>
      </Information>
      <Information>
        <Name>NFPA Fire Rating</Name>
        <Value><StringWithMarkup><String>3 - Flammable</String></StringWithMarkup></Value>
      </Information>
    </Section>
  </Record>
</Records>
"""
    path = Path(temp_bulk_dir) / "CID-LCSS.xml.gz"
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
def all_fixtures(fixture_identifiers_gz, fixture_synonyms_gz, fixture_lcss_xml_gz,
                 fixture_smiles_gz, fixture_title_gz):
    """Bundle all fixture files."""
    return {
        "identifiers": fixture_identifiers_gz,
        "synonyms": fixture_synonyms_gz,
        "lcss": fixture_lcss_xml_gz,
        "smiles": fixture_smiles_gz,
        "title": fixture_title_gz,
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

    def test_offline_mode_env(self, monkeypatch):
        """Test PUBCHEM_OFFLINE_MODE environment variable."""
        monkeypatch.setenv("PUBCHEM_OFFLINE_MODE", "1")
        pubchem_bulk._offline_mode = None
        assert pubchem_bulk._is_offline_mode() is True


class TestCasValidation:
    """Test CAS number validation."""

    def test_valid_cas_numbers(self):
        """Test recognition of valid CAS numbers."""
        valid_cases = [
            "67-64-1",
            "64-17-5",
            "7782-50-5",
            "50-00-0",
            "1-23-4",
            "1234567-89-0",
        ]
        for cas in valid_cases:
            assert pubchem_bulk._is_valid_cas(cas), f"{cas} should be valid"

    def test_invalid_cas_numbers(self):
        """Test rejection of invalid CAS numbers."""
        invalid_cases = [
            "Acetone",
            "C2H5OH",
            "123456789-12-3",
            "12345-123-1",
            "12345-12-12",
            "",
            "abc-de-f",
        ]
        for cas in invalid_cases:
            assert not pubchem_bulk._is_valid_cas(cas), f"{cas} should be invalid"


class TestMultiCidResolution:
    """Test multi-CID resolution rules."""

    def test_resolve_single_candidate(self):
        """Single candidate returns as-is."""
        cid, source, ambig = pubchem_bulk._resolve_best_cid([(180, "identifiers")])
        assert cid == 180
        assert source == "identifiers"
        assert ambig is False

    def test_resolve_prefers_identifiers_over_synonyms(self):
        """Identifiers source takes priority over synonyms."""
        candidates = [
            (12345, "synonyms"),
            (180, "identifiers"),
            (99999, "synonyms"),
        ]
        cid, source, ambig = pubchem_bulk._resolve_best_cid(candidates)
        assert cid == 180
        assert source == "identifiers"
        assert ambig is True

    def test_resolve_prefers_lowest_cid_same_source(self):
        """Among same-source candidates, prefer lowest CID."""
        candidates = [
            (99999, "synonyms"),
            (180, "synonyms"),
            (12345, "synonyms"),
        ]
        cid, source, ambig = pubchem_bulk._resolve_best_cid(candidates)
        assert cid == 180
        assert source == "synonyms"
        assert ambig is True

    def test_resolve_identifiers_lowest_cid(self):
        """Among multiple identifiers, prefer lowest CID."""
        candidates = [
            (500, "identifiers"),
            (100, "identifiers"),
            (300, "identifiers"),
        ]
        cid, source, ambig = pubchem_bulk._resolve_best_cid(candidates)
        assert cid == 100
        assert source == "identifiers"
        assert ambig is True


class TestCasMappingCollection:
    """Test CAS → CID mapping collection from both sources."""

    def test_collect_from_identifiers_only(self, temp_bulk_dir, fixture_identifiers_gz):
        """Test collection from CID-Identifiers only."""
        cas_to_cids, count = pubchem_bulk._collect_cas_cid_mappings(
            fixture_identifiers_gz, None, None
        )

        assert "67-64-1" in cas_to_cids
        assert cas_to_cids["67-64-1"] == [(180, "identifiers")]
        assert count >= 10

    def test_collect_from_both_sources(self, temp_bulk_dir, fixture_identifiers_gz, fixture_synonyms_gz):
        """Test collection from both sources with multi-CID handling."""
        cas_to_cids, count = pubchem_bulk._collect_cas_cid_mappings(
            fixture_identifiers_gz, fixture_synonyms_gz, None
        )

        assert "67-64-1" in cas_to_cids
        cids = cas_to_cids["67-64-1"]
        assert (180, "identifiers") in cids
        assert (12345, "synonyms") in cids
        assert (99999, "synonyms") in cids

    def test_collect_with_cas_filter(self, temp_bulk_dir, fixture_identifiers_gz):
        """Test collection respects CAS filter."""
        cas_filter = {"67-64-1", "64-17-5"}
        cas_to_cids, count = pubchem_bulk._collect_cas_cid_mappings(
            fixture_identifiers_gz, None, cas_filter
        )

        assert "67-64-1" in cas_to_cids
        assert "64-17-5" in cas_to_cids
        assert "7782-50-5" not in cas_to_cids


class TestIndexBuilding:
    """Test index building from fixture files."""

    def test_index_cas_mappings_with_ambiguity(self, temp_bulk_dir, fixture_identifiers_gz, fixture_synonyms_gz):
        """Test CAS indexing with ambiguous CID detection."""
        db_path = pubchem_bulk._get_index_db_path()
        conn = sqlite3.connect(str(db_path))
        pubchem_bulk._create_index_schema(conn)

        cas_to_cids, _ = pubchem_bulk._collect_cas_cid_mappings(
            fixture_identifiers_gz, fixture_synonyms_gz, None
        )
        total, ambiguous = pubchem_bulk._index_cas_mappings(conn, cas_to_cids)

        assert total > 0
        assert ambiguous > 0

        cur = conn.cursor()
        cur.execute("SELECT cid, cid_source, cid_ambiguous FROM cas_to_cid WHERE cas = ?", ("67-64-1",))
        row = cur.fetchone()
        assert row[0] == 180
        assert row[1] == "identifiers"
        assert row[2] == 1

        cur.execute("SELECT COUNT(*) FROM cas_cid_candidates WHERE cas = ?", ("67-64-1",))
        assert cur.fetchone()[0] >= 2

        conn.close()

    def test_index_lcss(self, temp_bulk_dir, fixture_lcss_xml_gz):
        """Test LCSS XML indexing."""
        db_path = pubchem_bulk._get_index_db_path()
        conn = sqlite3.connect(str(db_path))
        pubchem_bulk._create_index_schema(conn)

        count = pubchem_bulk._index_lcss(conn, fixture_lcss_xml_gz)
        assert count >= 2

        cur = conn.cursor()
        cur.execute("SELECT ghs_hcodes, nfpa_health, nfpa_fire, flash_point_c FROM cid_lcss WHERE cid = ?", (180,))
        row = cur.fetchone()
        assert row is not None

        hcodes = json.loads(row[0])
        assert "H225" in hcodes
        assert "H319" in hcodes
        assert row[1] == 1
        assert row[2] == 3
        assert row[3] == -20.0

        conn.close()


class TestLookups:
    """Test lookup functions with indexed data."""

    @pytest.fixture
    def indexed_db(self, temp_bulk_dir, all_fixtures):
        """Build a complete index from fixtures."""
        db_path = pubchem_bulk._get_index_db_path()
        conn = sqlite3.connect(str(db_path))
        pubchem_bulk._create_index_schema(conn)

        cas_to_cids, _ = pubchem_bulk._collect_cas_cid_mappings(
            all_fixtures["identifiers"], all_fixtures["synonyms"], None
        )
        pubchem_bulk._index_cas_mappings(conn, cas_to_cids)
        pubchem_bulk._index_lcss(conn, all_fixtures["lcss"])
        pubchem_bulk._index_smiles(conn, all_fixtures["smiles"])
        pubchem_bulk._index_titles(conn, all_fixtures["title"])

        conn.close()
        return db_path

    def test_lookup_cid_by_cas_found(self, indexed_db):
        """Test CAS → CID lookup when CAS exists."""
        cid = pubchem_bulk.lookup_cid_by_cas("67-64-1")
        assert cid == 180

    def test_lookup_cid_by_cas_not_found(self, indexed_db):
        """Test CAS → CID lookup for CAS absent from PubChem."""
        cid = pubchem_bulk.lookup_cid_by_cas("99999-99-9")
        assert cid is None

    def test_lookup_cas_mapping_details_ambiguous(self, indexed_db):
        """Test detailed CAS lookup with ambiguity info."""
        details = pubchem_bulk.lookup_cas_mapping_details("67-64-1")
        assert details is not None
        assert details["cid"] == 180
        assert details["cid_source"] == "identifiers"
        assert details["cid_ambiguous"] is True
        assert "candidates" in details
        assert len(details["candidates"]) >= 2

    def test_lookup_lcss_data(self, indexed_db):
        """Test LCSS hazard data lookup."""
        lcss = pubchem_bulk.lookup_lcss_data(180)
        assert lcss is not None
        assert "H225" in lcss["ghs_hcodes"]
        assert lcss["nfpa_health"] == 1
        assert lcss["nfpa_fire"] == 3
        assert lcss["flash_point_c"] == -20.0
        assert lcss["pubchem_source"] == "ftp_lcss"
        assert lcss["toxicity_sections"] == "absent"

    def test_lookup_cas_full(self, indexed_db):
        """Test combined CAS lookup with all data."""
        data = pubchem_bulk.lookup_cas_full("67-64-1")
        assert data is not None
        assert data["cid"] == 180
        assert data["smiles"] == "CC(=O)C"
        assert data["title"] == "Acetone"
        assert "H225" in data.get("ghs_hcodes", [])
        assert data["pubchem_source"] == "ftp_lcss"
        assert data["toxicity_sections"] == "absent"
        assert data["cid_ambiguous"] is True

    def test_lookup_cas_absent_from_pubchem(self, indexed_db):
        """Test lookup for CAS number not in PubChem returns None."""
        data = pubchem_bulk.lookup_cas_full("99999-99-9")
        assert data is None

    def test_lookup_disabled_returns_none(self, indexed_db, monkeypatch):
        """Test lookups return None when bulk is disabled."""
        monkeypatch.setenv("PUBCHEM_DISABLE_BULK", "1")
        pubchem_bulk._bulk_disabled = None

        assert pubchem_bulk.lookup_cid_by_cas("67-64-1") is None
        assert pubchem_bulk.lookup_lcss_data(180) is None


class TestStreamingParser:
    """Test streaming parser doesn't load entire file into memory."""

    def test_stream_gzip_lines_yields_lines(self, fixture_synonyms_gz):
        """Test streaming yields individual lines."""
        lines = list(pubchem_bulk._stream_gzip_lines(fixture_synonyms_gz))
        assert len(lines) > 0
        assert all(isinstance(line, str) for line in lines)

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


class TestFallbackIntegration:
    """Test integration with pubchem.py fallback behavior."""

    @pytest.fixture
    def indexed_db(self, temp_bulk_dir, all_fixtures):
        """Build a complete index from fixtures."""
        db_path = pubchem_bulk._get_index_db_path()
        conn = sqlite3.connect(str(db_path))
        pubchem_bulk._create_index_schema(conn)

        cas_to_cids, _ = pubchem_bulk._collect_cas_cid_mappings(
            all_fixtures["identifiers"], all_fixtures["synonyms"], None
        )
        pubchem_bulk._index_cas_mappings(conn, cas_to_cids)
        pubchem_bulk._index_smiles(conn, all_fixtures["smiles"])
        pubchem_bulk._index_lcss(conn, all_fixtures["lcss"])
        conn.close()
        return db_path

    def test_pubchem_get_cid_uses_bulk_first(self, indexed_db, monkeypatch):
        """Test get_cid_by_cas uses bulk index first."""
        from packages.doss_core import pubchem

        cache_dir = Path(indexed_db).parent / "api_cache"
        monkeypatch.setenv("PUBCHEM_CACHE_DIR", str(cache_dir))
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
        monkeypatch.setenv("PUBCHEM_OFFLINE_MODE", "0")
        pubchem._CACHE_DIR = None
        pubchem._MIN_INTERVAL_S = 0.01
        pubchem._offline_mode = None

        mock_resp = mock.Mock()
        mock_resp.status_code = 200
        mock_resp.headers = {}
        mock_resp.json.return_value = {"IdentifierList": {"CID": [12345]}}
        mock_resp.raise_for_status = mock.Mock()

        with mock.patch("requests.get", return_value=mock_resp) as mock_get:
            cid = pubchem.get_cid_by_cas("99999-99-9")
            mock_get.assert_called_once()
            assert cid == 12345


class TestOfflineMode:
    """Test offline mode behavior."""

    @pytest.fixture
    def indexed_db(self, temp_bulk_dir, all_fixtures):
        """Build a complete index from fixtures."""
        db_path = pubchem_bulk._get_index_db_path()
        conn = sqlite3.connect(str(db_path))
        pubchem_bulk._create_index_schema(conn)

        cas_to_cids, _ = pubchem_bulk._collect_cas_cid_mappings(
            all_fixtures["identifiers"], all_fixtures["synonyms"], None
        )
        pubchem_bulk._index_cas_mappings(conn, cas_to_cids)
        pubchem_bulk._index_smiles(conn, all_fixtures["smiles"])
        pubchem_bulk._index_lcss(conn, all_fixtures["lcss"])
        pubchem_bulk._index_titles(conn, all_fixtures["title"])
        conn.close()
        return db_path

    def test_offline_mode_blocks_downloads(self, temp_bulk_dir, monkeypatch):
        """Test offline mode blocks download attempts."""
        monkeypatch.setenv("PUBCHEM_OFFLINE_MODE", "1")
        pubchem_bulk._offline_mode = None

        result = pubchem_bulk._download_file(
            "https://example.com/test.gz",
            Path(temp_bulk_dir) / "test.gz"
        )
        assert result is False

    def test_offline_mode_fetch_compound_uses_bulk(self, indexed_db, monkeypatch):
        """Test fetch_compound_data uses bulk in offline mode."""
        from packages.doss_core import pubchem

        monkeypatch.setenv("PUBCHEM_OFFLINE_MODE", "1")
        pubchem._offline_mode = None

        with mock.patch("requests.get") as mock_get:
            data = pubchem.fetch_compound_data("67-64-1")
            mock_get.assert_not_called()

        assert data["cid"] == 180
        assert data["pubchem_source"] == "ftp_lcss"
        assert data["toxicity_sections"] == "absent"
        assert "H225" in data["ghs_hazards"]

    def test_offline_mode_raises_for_unknown_cas(self, indexed_db, monkeypatch):
        """Test fetch_compound_data raises PubChemOfflineError for unknown CAS."""
        from packages.doss_core import pubchem

        monkeypatch.setenv("PUBCHEM_OFFLINE_MODE", "1")
        pubchem._offline_mode = None

        with pytest.raises(pubchem.PubChemOfflineError):
            pubchem.fetch_compound_data("99999-99-9")


class TestIndexStatus:
    """Test index status reporting."""

    def test_status_no_index(self, temp_bulk_dir):
        """Test status when no index exists."""
        status = pubchem_bulk.get_index_status()
        assert status["db_exists"] is False

    def test_status_with_index(self, temp_bulk_dir, all_fixtures):
        """Test status after building index."""
        db_path = pubchem_bulk._get_index_db_path()
        conn = sqlite3.connect(str(db_path))
        pubchem_bulk._create_index_schema(conn)

        cas_to_cids, _ = pubchem_bulk._collect_cas_cid_mappings(
            all_fixtures["identifiers"], all_fixtures["synonyms"], None
        )
        pubchem_bulk._index_cas_mappings(conn, cas_to_cids)
        pubchem_bulk._index_lcss(conn, all_fixtures["lcss"])
        conn.close()

        status = pubchem_bulk.get_index_status()
        assert status["db_exists"] is True
        assert status["cas_count"] > 0
        assert status["ambiguous_cas_count"] > 0
        assert status["lcss_count"] > 0


class TestLcssXmlParsing:
    """Test LCSS XML parsing edge cases."""

    def test_parse_ghs_signal_word(self, fixture_lcss_xml_gz):
        """Test GHS signal word extraction."""
        for elem in pubchem_bulk._stream_xml_records(fixture_lcss_xml_gz, "Record"):
            data = pubchem_bulk._parse_lcss_record(elem)
            if data and data.get("cid") == 180:
                assert data.get("ghs_signal_word") == "Danger"
                break

    def test_parse_flash_point_fahrenheit_conversion(self, temp_bulk_dir):
        """Test flash point Fahrenheit to Celsius conversion."""
        content = """\
<?xml version="1.0" encoding="UTF-8"?>
<Records>
  <Record>
    <RecordNumber>999</RecordNumber>
    <Section>
      <TOCHeading>Physical Description</TOCHeading>
      <Information>
        <Name>Flash Point</Name>
        <Value><StringWithMarkup><String>100 °F</String></StringWithMarkup></Value>
      </Information>
    </Section>
  </Record>
</Records>
"""
        path = Path(temp_bulk_dir) / "test_lcss.xml.gz"
        with gzip.open(path, "wt", encoding="utf-8") as f:
            f.write(content)

        for elem in pubchem_bulk._stream_xml_records(path, "Record"):
            data = pubchem_bulk._parse_lcss_record(elem)
            if data:
                assert abs(data["flash_point_c"] - 37.8) < 0.1
