"""
Tests for packages.iuclid_core.

CRITICAL: All fixtures are SYNTHETIC - no actual ECHA dossier content is used.
These tests create minimal fake IUCLID XML that mirrors the structure.
"""

from __future__ import annotations

import io
import json
import logging
import os
import sqlite3
import tempfile
import zipfile
from pathlib import Path
from unittest import mock

import pytest


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "iuclid"


SYNTHETIC_ACUTE_ORAL_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="http://iuclid6.echa.europa.eu/document">
  <ENDPOINT_STUDY_RECORD.AcuteToxicityOral>
    <AdministrativeData>
      <StudyResultType><value>1895</value></StudyResultType>
      <PurposeFlag><value>921</value></PurposeFlag>
      <Reliability><value>18</value></Reliability>
    </AdministrativeData>
    <MaterialsAndMethods>
      <TestAnimals>
        <Species><value>3485</value></Species>
      </TestAnimals>
      <AdministrationExposure>
        <RouteOfAdministration><value>2231</value></RouteOfAdministration>
      </AdministrationExposure>
    </MaterialsAndMethods>
    <ResultsAndDiscussion>
      <EffectLevels>
        <entry>
          <KeyResult>true</KeyResult>
          <Endpoint><value>931</value></Endpoint>
          <EffectLevel>
            <lowerValue>4500</lowerValue>
            <unitCode>2081</unitCode>
          </EffectLevel>
          <Sex><value>2052</value></Sex>
        </entry>
      </EffectLevels>
    </ResultsAndDiscussion>
  </ENDPOINT_STUDY_RECORD.AcuteToxicityOral>
</Document>
"""


SYNTHETIC_AQUATIC_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="http://iuclid6.echa.europa.eu/document">
  <ENDPOINT_STUDY_RECORD.ToxicityToAquaticAlgae>
    <AdministrativeData>
      <StudyResultType><value>1895</value></StudyResultType>
      <PurposeFlag><value>921</value></PurposeFlag>
      <Reliability><value>18</value></Reliability>
    </AdministrativeData>
    <MaterialsAndMethods>
      <TestOrganisms>
        <TestOrganismsSpecies><value>3895</value></TestOrganismsSpecies>
      </TestOrganisms>
    </MaterialsAndMethods>
    <ResultsAndDiscussion>
      <EffectConcentrations>
        <entry>
          <KeyResult>false</KeyResult>
          <Endpoint><value>365</value></Endpoint>
          <EffectConc>
            <lowerValue>5600</lowerValue>
            <unitCode>2098</unitCode>
          </EffectConc>
          <Duration>
            <lowerValue>48</lowerValue>
            <unitCode>1976</unitCode>
          </Duration>
        </entry>
        <entry>
          <KeyResult>false</KeyResult>
          <Endpoint><value>1129</value></Endpoint>
          <EffectConc>
            <lowerQualifier>></lowerQualifier>
            <lowerValue>1000</lowerValue>
            <unitCode>2098</unitCode>
          </EffectConc>
          <Duration>
            <lowerValue>48</lowerValue>
            <unitCode>1976</unitCode>
          </Duration>
        </entry>
      </EffectConcentrations>
    </ResultsAndDiscussion>
  </ENDPOINT_STUDY_RECORD.ToxicityToAquaticAlgae>
</Document>
"""


SYNTHETIC_FLASH_POINT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="http://iuclid6.echa.europa.eu/document">
  <ENDPOINT_STUDY_RECORD.FlashPoint>
    <AdministrativeData>
      <StudyResultType><value>1895</value></StudyResultType>
      <PurposeFlag><value>921</value></PurposeFlag>
      <Reliability><value>16</value></Reliability>
    </AdministrativeData>
    <MaterialsAndMethods/>
    <ResultsAndDiscussion>
      <FlashPoint>
        <entry>
          <FPoint>
            <lowerValue>-4.5</lowerValue>
            <unitCode>2493</unitCode>
          </FPoint>
        </entry>
      </FlashPoint>
    </ResultsAndDiscussion>
  </ENDPOINT_STUDY_RECORD.FlashPoint>
</Document>
"""


SYNTHETIC_VAPOUR_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="http://iuclid6.echa.europa.eu/document">
  <ENDPOINT_STUDY_RECORD.Vapour>
    <AdministrativeData>
      <StudyResultType><value>1895</value></StudyResultType>
      <PurposeFlag><value>921</value></PurposeFlag>
      <Reliability><value>18</value></Reliability>
    </AdministrativeData>
    <MaterialsAndMethods/>
    <ResultsAndDiscussion>
      <Vapourpr>
        <entry>
          <Pressure>
            <lowerValue>93.2</lowerValue>
            <unitCode>2121</unitCode>
          </Pressure>
          <TempQualifier>
            <lowerValue>25</lowerValue>
            <unitCode>2493</unitCode>
          </TempQualifier>
        </entry>
      </Vapourpr>
    </ResultsAndDiscussion>
  </ENDPOINT_STUDY_RECORD.Vapour>
</Document>
"""


SYNTHETIC_PARTITION_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="http://iuclid6.echa.europa.eu/document">
  <ENDPOINT_STUDY_RECORD.Partition>
    <AdministrativeData>
      <StudyResultType><value>1895</value></StudyResultType>
      <PurposeFlag><value>921</value></PurposeFlag>
      <Reliability><value>18</value></Reliability>
    </AdministrativeData>
    <MaterialsAndMethods/>
    <ResultsAndDiscussion>
      <Partcoeff>
        <entry>
          <Type><value>2043</value></Type>
          <Partition>
            <lowerValue>0.73</lowerValue>
          </Partition>
          <Temp>
            <lowerValue>20</lowerValue>
            <unitCode>2493</unitCode>
          </Temp>
        </entry>
      </Partcoeff>
    </ResultsAndDiscussion>
  </ENDPOINT_STUDY_RECORD.Partition>
</Document>
"""


SYNTHETIC_UNRELIABLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="http://iuclid6.echa.europa.eu/document">
  <ENDPOINT_STUDY_RECORD.AcuteToxicityOral>
    <AdministrativeData>
      <StudyResultType><value>1895</value></StudyResultType>
      <PurposeFlag><value>1590</value></PurposeFlag>
      <Reliability><value>22</value></Reliability>
    </AdministrativeData>
    <MaterialsAndMethods>
      <TestAnimals>
        <Species><value>3485</value></Species>
      </TestAnimals>
      <AdministrationExposure>
        <RouteOfAdministration><value>2231</value></RouteOfAdministration>
      </AdministrationExposure>
    </MaterialsAndMethods>
    <ResultsAndDiscussion>
      <EffectLevels>
        <entry>
          <KeyResult>false</KeyResult>
          <Endpoint><value>931</value></Endpoint>
          <EffectLevel>
            <lowerValue>100</lowerValue>
            <unitCode>2081</unitCode>
          </EffectLevel>
        </entry>
      </EffectLevels>
    </ResultsAndDiscussion>
  </ENDPOINT_STUDY_RECORD.AcuteToxicityOral>
</Document>
"""


def create_synthetic_i6z(documents: dict[str, str]) -> io.BytesIO:
    """Create a synthetic .i6z (ZIP) containing the given XML documents."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in documents.items():
            zf.writestr(name, content.encode("utf-8"))
    buffer.seek(0)
    return buffer


class TestPhraseMapper:
    """Tests for phrase_mapper module."""

    def test_bundled_phrases_loaded(self):
        """Bundled phrase map should have common codes."""
        from packages.iuclid_core.phrase_mapper import BUNDLED_PHRASES
        
        assert "2081" in BUNDLED_PHRASES
        assert BUNDLED_PHRASES["2081"] == "mg/kg bw"
        assert "2098" in BUNDLED_PHRASES
        assert BUNDLED_PHRASES["2098"] == "mg/L"
        assert "931" in BUNDLED_PHRASES
        assert BUNDLED_PHRASES["931"] == "LD50"

    def test_phrase_mapper_decode(self):
        """PhraseMapper should decode known codes."""
        from packages.iuclid_core.phrase_mapper import PhraseMapper
        
        mapper = PhraseMapper()
        assert mapper.decode("2081") == "mg/kg bw"
        assert mapper.decode("931") == "LD50"
        assert mapper.decode("unknown_code") == "unknown_code"
        assert mapper.decode("") == ""
        assert mapper.decode(None) == ""

    def test_phrase_mapper_from_json(self):
        """PhraseMapper should load from JSON file."""
        from packages.iuclid_core.phrase_mapper import PhraseMapper
        
        json_path = FIXTURES_DIR / "synthetic_phrases.json"
        mapper = PhraseMapper.from_json(json_path)
        
        assert mapper.decode("18") == "2 (reliable with restrictions)"
        assert mapper.decode("365") == "EC50"

    def test_java_unescape(self):
        """Should unescape Java unicode escapes."""
        from packages.iuclid_core.phrase_mapper import _java_unescape
        
        assert _java_unescape("\\u00B0C") == "°C"
        assert _java_unescape("normal text") == "normal text"
        assert _java_unescape("\\u00B5g/L") == "µg/L"


class TestExtractor:
    """Tests for extractor module."""

    def test_extract_acute_oral(self):
        """Should extract acute oral toxicity endpoints."""
        from packages.iuclid_core.extractor import extract_dossier
        from packages.iuclid_core.phrase_mapper import PhraseMapper
        
        i6z = create_synthetic_i6z({
            "acute_oral_001.i6d": SYNTHETIC_ACUTE_ORAL_XML,
        })
        
        phrases = PhraseMapper.from_json(FIXTURES_DIR / "synthetic_phrases.json")
        records = extract_dossier(i6z, "synthetic-001", phrases)
        
        assert len(records) == 1
        rec = records[0]
        assert rec.subtype == "AcuteToxicityOral"
        assert rec.endpoint == "LD50"
        assert rec.value is not None
        assert rec.value.lower == 4500.0
        assert rec.value.unit == "mg/kg bw"
        assert rec.reliability == "2 (reliable with restrictions)"
        assert rec.species == "rat"
        assert "oral" in rec.route.lower()
        assert rec.key_result is True

    def test_extract_aquatic_algae(self):
        """Should extract aquatic toxicity endpoints including EC50."""
        from packages.iuclid_core.extractor import extract_dossier
        from packages.iuclid_core.phrase_mapper import PhraseMapper
        
        i6z = create_synthetic_i6z({
            "algae_001.i6d": SYNTHETIC_AQUATIC_XML,
        })
        
        phrases = PhraseMapper.from_json(FIXTURES_DIR / "synthetic_phrases.json")
        records = extract_dossier(i6z, "synthetic-002", phrases)
        
        assert len(records) == 2
        
        ec50_rec = next((r for r in records if r.endpoint == "EC50"), None)
        assert ec50_rec is not None
        assert ec50_rec.subtype == "ToxicityToAquaticAlgae"
        assert ec50_rec.value.lower == 5600.0
        assert ec50_rec.value.unit == "mg/L"
        assert ec50_rec.duration is not None
        assert ec50_rec.duration.lower == 48.0
        assert ec50_rec.duration.unit == "h"
        
        noec_rec = next((r for r in records if r.endpoint == "NOEC"), None)
        assert noec_rec is not None
        assert noec_rec.value.lower_qualifier == ">"
        assert noec_rec.value.lower == 1000.0

    def test_extract_flash_point(self):
        """Should extract flash point."""
        from packages.iuclid_core.extractor import extract_dossier
        from packages.iuclid_core.phrase_mapper import PhraseMapper
        
        i6z = create_synthetic_i6z({
            "flash_001.i6d": SYNTHETIC_FLASH_POINT_XML,
        })
        
        phrases = PhraseMapper.from_json(FIXTURES_DIR / "synthetic_phrases.json")
        records = extract_dossier(i6z, "synthetic-003", phrases)
        
        assert len(records) == 1
        rec = records[0]
        assert rec.subtype == "FlashPoint"
        assert rec.value.lower == -4.5
        assert rec.value.unit == "°C"
        assert rec.reliability == "1 (reliable without restriction)"

    def test_extract_vapour_pressure(self):
        """Should extract vapour pressure."""
        from packages.iuclid_core.extractor import extract_dossier
        from packages.iuclid_core.phrase_mapper import PhraseMapper
        
        i6z = create_synthetic_i6z({
            "vapour_001.i6d": SYNTHETIC_VAPOUR_XML,
        })
        
        phrases = PhraseMapper.from_json(FIXTURES_DIR / "synthetic_phrases.json")
        records = extract_dossier(i6z, "synthetic-004", phrases)
        
        assert len(records) == 1
        rec = records[0]
        assert rec.subtype == "Vapour"
        assert rec.value.lower == 93.2
        assert rec.value.unit == "mm Hg"
        assert "tempqualifier" in rec.extras
        assert rec.extras["tempqualifier"]["lower"] == 25.0

    def test_extract_log_kow(self):
        """Should extract partition coefficient (log Kow)."""
        from packages.iuclid_core.extractor import extract_dossier
        from packages.iuclid_core.phrase_mapper import PhraseMapper
        
        i6z = create_synthetic_i6z({
            "partition_001.i6d": SYNTHETIC_PARTITION_XML,
        })
        
        phrases = PhraseMapper.from_json(FIXTURES_DIR / "synthetic_phrases.json")
        records = extract_dossier(i6z, "synthetic-005", phrases)
        
        assert len(records) == 1
        rec = records[0]
        assert rec.subtype == "Partition"
        assert rec.value.lower == 0.73
        assert "type" in rec.extras
        type_val = rec.extras["type"]
        if isinstance(type_val, str):
            assert "log" in type_val.lower()
        else:
            assert type_val == "log Pow"

    def test_extract_multiple_documents(self):
        """Should extract from multiple documents in one dossier."""
        from packages.iuclid_core.extractor import extract_dossier
        from packages.iuclid_core.phrase_mapper import PhraseMapper
        
        i6z = create_synthetic_i6z({
            "acute_oral_001.i6d": SYNTHETIC_ACUTE_ORAL_XML,
            "algae_001.i6d": SYNTHETIC_AQUATIC_XML,
            "flash_001.i6d": SYNTHETIC_FLASH_POINT_XML,
        })
        
        phrases = PhraseMapper.from_json(FIXTURES_DIR / "synthetic_phrases.json")
        records = extract_dossier(i6z, "synthetic-multi", phrases)
        
        subtypes = {r.subtype for r in records}
        assert "AcuteToxicityOral" in subtypes
        assert "ToxicityToAquaticAlgae" in subtypes
        assert "FlashPoint" in subtypes

    def test_reliability_score_extraction(self):
        """Should correctly extract Klimisch reliability scores."""
        from packages.iuclid_core.extractor import extract_dossier
        from packages.iuclid_core.phrase_mapper import PhraseMapper
        
        i6z = create_synthetic_i6z({
            "reliable.i6d": SYNTHETIC_ACUTE_ORAL_XML,
            "unreliable.i6d": SYNTHETIC_UNRELIABLE_XML,
        })
        
        phrases = PhraseMapper.from_json(FIXTURES_DIR / "synthetic_phrases.json")
        records = extract_dossier(i6z, "synthetic-rel", phrases)
        
        reliable = [r for r in records if r.reliability_score == 2]
        unreliable = [r for r in records if r.reliability_score == 3]
        
        assert len(reliable) == 1
        assert reliable[0].is_reliable is True
        assert len(unreliable) == 1
        assert unreliable[0].is_reliable is False


class TestIndex:
    """Tests for index module."""

    def test_normalize_cas(self):
        """Should normalize various CAS formats."""
        from packages.iuclid_core.index import normalize_cas
        
        assert normalize_cas("71-43-2") == "71-43-2"
        assert normalize_cas("071-43-2") == "71-43-2"
        assert normalize_cas("71432") == "71-43-2"
        assert normalize_cas("0071432") == "71-43-2"
        assert normalize_cas("") == ""

    def test_load_csv_index(self):
        """Should load CAS → UUID mapping from CSV."""
        from packages.iuclid_core.index import _load_csv_index
        
        csv_path = FIXTURES_DIR / "synthetic_index.csv"
        cas_to_uuids = _load_csv_index(csv_path)
        
        assert "12345-67-8" in cas_to_uuids
        assert len(cas_to_uuids["12345-67-8"]) == 2
        assert "00000000-0000-0000-0000-000000000001" in cas_to_uuids["12345-67-8"]
        assert "00000000-0000-0000-0000-000000000002" in cas_to_uuids["12345-67-8"]
        
        assert "98765-43-2" in cas_to_uuids
        assert len(cas_to_uuids["98765-43-2"]) == 1


class TestConfig:
    """Tests for config module."""

    def test_disabled_when_not_configured(self):
        """Should be disabled when IUCLID_DOSSIER_SOURCE not set."""
        from packages.iuclid_core.config import get_config, reset_config_log
        
        reset_config_log()
        
        with mock.patch.dict(os.environ, {}, clear=True):
            os.environ.pop("IUCLID_DOSSIER_SOURCE", None)
            os.environ.pop("OFFLINE_LOCAL_ARCHIVE", None)
            
            config = get_config()
            
            assert config.enabled is False
            assert config.disable_reason is not None
            assert "IUCLID_DOSSIER_SOURCE not set" in config.disable_reason

    def test_disabled_when_explicitly_false(self):
        """Should be disabled when IUCLID_ENABLED=false."""
        from packages.iuclid_core.config import get_config, reset_config_log
        
        reset_config_log()
        
        with mock.patch.dict(os.environ, {"IUCLID_ENABLED": "false"}, clear=True):
            config = get_config()
            
            assert config.enabled is False
            assert config.disable_reason == "IUCLID_ENABLED=false"

    def test_logs_disable_reason_once(self, caplog):
        """Should log disable reason once, not on every call."""
        from packages.iuclid_core.config import get_config, reset_config_log
        
        reset_config_log()
        
        with mock.patch.dict(os.environ, {}, clear=True):
            os.environ.pop("IUCLID_DOSSIER_SOURCE", None)
            os.environ.pop("OFFLINE_LOCAL_ARCHIVE", None)
            
            with caplog.at_level(logging.INFO, logger="packages.iuclid_core.config"):
                get_config()
                initial_count = len(caplog.records)
                
                get_config()
                get_config()
                
                assert len(caplog.records) == initial_count

    def test_legacy_env_var_alias(self):
        """Should support OFFLINE_LOCAL_ARCHIVE as alias."""
        from packages.iuclid_core.config import _get_env
        
        with mock.patch.dict(
            os.environ,
            {"OFFLINE_LOCAL_ARCHIVE": "/some/path"},
            clear=True,
        ):
            val = _get_env("IUCLID_DOSSIER_SOURCE", "OFFLINE_LOCAL_ARCHIVE")
            assert val == "/some/path"

    def test_get_status(self):
        """get_status should return detailed info."""
        from packages.iuclid_core.config import get_status, reset_config_log
        
        reset_config_log()
        
        with mock.patch.dict(os.environ, {}, clear=True):
            status = get_status()
            
            assert "enabled" in status
            assert "disable_reason" in status
            assert "cache_dir" in status


class TestCache:
    """Tests for cache module."""

    def test_cache_store_and_retrieve(self):
        """Should store and retrieve endpoints."""
        from packages.iuclid_core.cache import IUCLIDCache
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_cache.db"
            cache = IUCLIDCache(db_path)
            
            endpoints = [
                {
                    "subtype": "AcuteToxicityOral",
                    "endpoint": "LD50",
                    "value": {"lower": 4500, "unit": "mg/kg bw"},
                },
                {
                    "subtype": "FlashPoint",
                    "value": {"lower": -4.5, "unit": "°C"},
                },
            ]
            
            count = cache.store_endpoints(
                "12345-67-8",
                "test-uuid-001",
                endpoints,
            )
            assert count == 2
            
            retrieved = cache.get_endpoints_for_cas("12345-67-8")
            assert len(retrieved) == 2
            
            retrieved_by_uuid = cache.get_endpoints_for_uuid("test-uuid-001")
            assert len(retrieved_by_uuid) == 2

    def test_cache_status(self):
        """Should return accurate status."""
        from packages.iuclid_core.cache import IUCLIDCache
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_cache.db"
            cache = IUCLIDCache(db_path)
            
            cache.store_endpoints("cas-1", "uuid-1", [{"subtype": "A"}])
            cache.store_endpoints("cas-2", "uuid-2", [{"subtype": "B"}, {"subtype": "C"}])
            
            status = cache.get_status()
            
            assert status["endpoint_count"] == 3
            assert status["uuid_count"] == 2
            assert status["cas_count"] == 2

    def test_cache_is_uuid_processed(self):
        """Should track processed UUIDs."""
        from packages.iuclid_core.cache import IUCLIDCache, EXTRACTOR_VERSION
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_cache.db"
            cache = IUCLIDCache(db_path)
            
            assert cache.is_uuid_processed("uuid-new") is False
            
            cache.store_endpoints("cas-1", "uuid-new", [{"subtype": "A"}])
            
            assert cache.is_uuid_processed("uuid-new") is True
            assert cache.is_uuid_processed("uuid-new", "old-version") is False

    def test_cache_clear(self):
        """Should clear all data."""
        from packages.iuclid_core.cache import IUCLIDCache
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_cache.db"
            cache = IUCLIDCache(db_path)
            
            cache.store_endpoints("cas-1", "uuid-1", [{"subtype": "A"}])
            assert cache.get_status()["endpoint_count"] == 1
            
            cache.clear()
            
            assert cache.get_status()["endpoint_count"] == 0


class TestBridge:
    """Tests for bridge module."""

    def test_select_min_ld50(self):
        """Should select minimum LD50 value."""
        from packages.iuclid_core.bridge import endpoints_to_extra_sources
        
        endpoints = [
            {
                "subtype": "AcuteToxicityOral",
                "endpoint": "LD50",
                "value": {"lower": 5000, "unit": "mg/kg bw"},
                "reliability": "2 (reliable with restrictions)",
                "species": "rat",
                "route": "oral: gavage",
                "dossier_uuid": "uuid-1",
            },
            {
                "subtype": "AcuteToxicityOral",
                "endpoint": "LD50",
                "value": {"lower": 4500, "unit": "mg/kg bw"},
                "reliability": "2 (reliable with restrictions)",
                "species": "rabbit",
                "route": "oral: gavage",
                "dossier_uuid": "uuid-2",
            },
        ]
        
        result = endpoints_to_extra_sources(endpoints, "12345-67-8")
        
        assert result is not None
        assert len(result["toxicities"]) == 1
        tox = result["toxicities"][0]
        assert "4500" in tox["value"]
        assert tox["source"] == "IUCLID"
        assert tox["predicted"] is False

    def test_reject_unreliable(self):
        """Should reject Klimisch 3/4 endpoints."""
        from packages.iuclid_core.bridge import endpoints_to_extra_sources
        
        endpoints = [
            {
                "subtype": "AcuteToxicityOral",
                "endpoint": "LD50",
                "value": {"lower": 100, "unit": "mg/kg bw"},
                "reliability": "3 (not reliable)",
                "species": "rat",
                "route": "oral: gavage",
                "dossier_uuid": "uuid-1",
            },
        ]
        
        result = endpoints_to_extra_sources(endpoints, "12345-67-8")
        
        assert result is None or len(result.get("toxicities", [])) == 0
        if result:
            assert len(result["rejected"]) == 1
            assert "not acceptable" in result["rejected"][0]["reason"]

    def test_reject_ml_kg_without_density(self):
        """Should reject mL/kg values without density conversion."""
        from packages.iuclid_core.bridge import endpoints_to_extra_sources
        
        endpoints = [
            {
                "subtype": "AcuteToxicityOral",
                "endpoint": "LD50",
                "value": {"lower": 11.3, "unit": "mL/kg bw"},
                "reliability": "2 (reliable with restrictions)",
                "species": "rat",
                "route": "oral: gavage",
                "dossier_uuid": "uuid-1",
            },
        ]
        
        result = endpoints_to_extra_sources(endpoints, "12345-67-8")
        
        assert result is None or len(result.get("toxicities", [])) == 0
        if result:
            assert any("density" in r["reason"].lower() for r in result["rejected"])

    def test_aquatic_valid_endpoints_only(self):
        """Should only use LC50/EC50/IC50 for aquatic, not NOEC."""
        from packages.iuclid_core.bridge import endpoints_to_extra_sources
        
        endpoints = [
            {
                "subtype": "ToxicityToAquaticAlgae",
                "endpoint": "EC50",
                "value": {"lower": 5600, "unit": "mg/L"},
                "reliability": "2 (reliable with restrictions)",
                "species": "Desmodesmus subspicatus",
                "dossier_uuid": "uuid-1",
            },
            {
                "subtype": "ToxicityToAquaticAlgae",
                "endpoint": "NOEC",
                "value": {"lower": 1000, "unit": "mg/L"},
                "reliability": "2 (reliable with restrictions)",
                "species": "Desmodesmus subspicatus",
                "dossier_uuid": "uuid-2",
            },
        ]
        
        result = endpoints_to_extra_sources(endpoints, "12345-67-8")
        
        assert result is not None
        aquatic_tox = [t for t in result["toxicities"] if "aquatic" in t["species_route"]]
        assert len(aquatic_tox) == 1
        assert "EC50" in aquatic_tox[0]["value"]

    def test_flash_point_extraction(self):
        """Should extract flash point in °C."""
        from packages.iuclid_core.bridge import endpoints_to_extra_sources
        
        endpoints = [
            {
                "subtype": "FlashPoint",
                "value": {"lower": -4.5, "unit": "°C"},
                "reliability": "1 (reliable without restriction)",
                "dossier_uuid": "uuid-1",
            },
        ]
        
        result = endpoints_to_extra_sources(endpoints, "12345-67-8")
        
        assert result is not None
        assert "flash_point_c" in result["hazard_metrics"]
        assert result["hazard_metrics"]["flash_point_c"]["value"] == -4.5
        assert result["hazard_metrics"]["flash_point_c"]["predicted"] is False

    def test_vapour_pressure_conversion(self):
        """Should convert vapour pressure to mm Hg."""
        from packages.iuclid_core.bridge import endpoints_to_extra_sources
        
        endpoints = [
            {
                "subtype": "Vapour",
                "value": {"lower": 10.0, "unit": "kPa"},
                "reliability": "2 (reliable with restrictions)",
                "dossier_uuid": "uuid-1",
            },
        ]
        
        result = endpoints_to_extra_sources(endpoints, "12345-67-8")
        
        assert result is not None
        assert "vapor_pressure_mmhg" in result["hazard_metrics"]
        vp = result["hazard_metrics"]["vapor_pressure_mmhg"]
        assert vp["value"] == pytest.approx(75.0062, rel=0.01)
        assert vp["original_unit"] == "kPa"

    def test_log_kow_extraction(self):
        """Should extract log Kow."""
        from packages.iuclid_core.bridge import endpoints_to_extra_sources
        
        endpoints = [
            {
                "subtype": "Partition",
                "value": {"lower": 0.73},
                "extras": {"type": "log Pow"},
                "reliability": "2 (reliable with restrictions)",
                "dossier_uuid": "uuid-1",
            },
        ]
        
        result = endpoints_to_extra_sources(endpoints, "12345-67-8")
        
        assert result is not None
        assert "log_kow" in result["hazard_metrics"]
        assert result["hazard_metrics"]["log_kow"]["value"] == 0.73

    def test_source_info_included(self):
        """Should include source info in result."""
        from packages.iuclid_core.bridge import endpoints_to_extra_sources
        
        endpoints = [
            {
                "subtype": "FlashPoint",
                "value": {"lower": -4.5, "unit": "°C"},
                "reliability": "2 (reliable with restrictions)",
                "dossier_uuid": "uuid-1",
            },
        ]
        
        result = endpoints_to_extra_sources(endpoints, "12345-67-8")
        
        assert result is not None
        assert "source_info" in result
        assert result["source_info"]["source"] == "ECHA REACH Study Results (IUCLID)"
        assert result["source_info"]["basis"] == "measured"
        assert result["source_info"]["cas"] == "12345-67-8"


class TestValidationReference:
    """Validation tests matching expected values from IUCLID_NOTES.md."""

    def test_ethyl_acetate_algae_ec50_reference(self):
        """
        Validation reference from IUCLID_NOTES.md:
        ethyl acetate algae EC50 5600 mg/L at 48h, reliability 2
        """
        from packages.iuclid_core.extractor import extract_dossier
        from packages.iuclid_core.phrase_mapper import PhraseMapper
        
        i6z = create_synthetic_i6z({
            "algae_ethyl_acetate.i6d": SYNTHETIC_AQUATIC_XML,
        })
        
        phrases = PhraseMapper.from_json(FIXTURES_DIR / "synthetic_phrases.json")
        records = extract_dossier(i6z, "ethyl-acetate-test", phrases)
        
        ec50_records = [r for r in records if r.endpoint == "EC50"]
        assert len(ec50_records) >= 1
        
        ec50 = ec50_records[0]
        assert ec50.value.lower == 5600.0
        assert ec50.value.unit == "mg/L"
        assert ec50.duration.lower == 48.0
        assert ec50.reliability_score == 2


class TestIntegration:
    """Integration tests for full workflow."""

    def test_full_extraction_and_bridge(self):
        """Test full workflow: extract → cache → bridge."""
        from packages.iuclid_core.extractor import extract_dossier
        from packages.iuclid_core.phrase_mapper import PhraseMapper
        from packages.iuclid_core.bridge import endpoints_to_extra_sources
        from packages.iuclid_core.cache import IUCLIDCache
        
        i6z = create_synthetic_i6z({
            "acute_oral.i6d": SYNTHETIC_ACUTE_ORAL_XML,
            "aquatic.i6d": SYNTHETIC_AQUATIC_XML,
            "flash.i6d": SYNTHETIC_FLASH_POINT_XML,
            "vapour.i6d": SYNTHETIC_VAPOUR_XML,
            "partition.i6d": SYNTHETIC_PARTITION_XML,
        })
        
        phrases = PhraseMapper.from_json(FIXTURES_DIR / "synthetic_phrases.json")
        records = extract_dossier(i6z, "full-test-uuid", phrases)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_cache.db"
            cache = IUCLIDCache(db_path)
            
            endpoints_dicts = [r.to_dict() for r in records]
            cache.store_endpoints("12345-67-8", "full-test-uuid", endpoints_dicts)
            
            cached = cache.get_endpoints_for_cas("12345-67-8")
            assert len(cached) == len(records)
        
        result = endpoints_to_extra_sources(endpoints_dicts, "12345-67-8")
        
        assert result is not None
        assert len(result["toxicities"]) >= 2
        assert "flash_point_c" in result["hazard_metrics"]
        assert "vapor_pressure_mmhg" in result["hazard_metrics"]
        assert "log_kow" in result["hazard_metrics"]
        assert result["source_info"]["basis"] == "measured"
