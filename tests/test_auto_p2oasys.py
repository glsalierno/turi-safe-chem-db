"""
Tests for auto_p2oasys package.

Acceptance criteria:
1. auto_p2oasys("67-64-1") returns mode `expert` from lookup (offline)
2. auto_p2oasys("67-64-1", force_fast=True) returns `expert+fast` with trace and source report
3. CAS not in lookup runs fast on fixtures, reproduces golden fixture scores
4. SDS fixture PDF yields CAS list and section-9 flash point as evidence with section reference
5. Capability report shows every adapter with status
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


os.environ["AUTO_P2OASYS_OFFLINE"] = "1"


class TestCasUtils:
    """Tests for CAS number utilities."""

    def test_normalize_cas(self):
        from packages.auto_p2oasys.cas_utils import normalize_cas

        assert normalize_cas("67-64-1") == "67641"
        assert normalize_cas("67641") == "67641"
        assert normalize_cas("7732-18-5") == "7732185"
        assert normalize_cas(None) == ""
        assert normalize_cas("") == ""

    def test_format_cas_display(self):
        from packages.auto_p2oasys.cas_utils import format_cas_display

        assert format_cas_display("67641") == "67-64-1"
        assert format_cas_display("67-64-1") == "67-64-1"
        assert format_cas_display("7732185") == "7732-18-5"

    def test_validate_cas_checksum_valid(self):
        from packages.auto_p2oasys.cas_utils import validate_cas_checksum

        assert validate_cas_checksum("67-64-1") is True
        assert validate_cas_checksum("7732-18-5") is True
        assert validate_cas_checksum("56-81-5") is True

    def test_validate_cas_checksum_invalid(self):
        from packages.auto_p2oasys.cas_utils import validate_cas_checksum

        assert validate_cas_checksum("67-64-2") is False
        assert validate_cas_checksum("12-34-5") is False
        assert validate_cas_checksum("1234") is False

    def test_extract_cas_from_text(self):
        from packages.auto_p2oasys.cas_utils import extract_cas_from_text

        text = "Contains acetone (67-64-1) and water (7732-18-5)"
        cas_list = extract_cas_from_text(text)
        assert "67-64-1" in cas_list
        assert "7732-18-5" in cas_list

        text_invalid = "Invalid CAS 12-34-5 and 99-99-9"
        cas_list = extract_cas_from_text(text_invalid)
        assert len(cas_list) == 0


class TestEvidence:
    """Tests for Evidence dataclass."""

    def test_evidence_creation(self):
        from packages.auto_p2oasys.evidence import Evidence

        ev = Evidence(
            cas="67-64-1",
            endpoint="flash_point",
            value=-17.8,
            unit="°C",
            source="PubChem",
            predicted=False,
        )
        assert ev.cas == "67-64-1"
        assert ev.endpoint == "flash_point"
        assert ev.value == -17.8
        assert ev.predicted is False

    def test_evidence_to_dict(self):
        from packages.auto_p2oasys.evidence import Evidence

        ev = Evidence(
            cas="67-64-1",
            endpoint="flash_point",
            value=-17.8,
            unit="°C",
            source="PubChem",
        )
        d = ev.to_dict()
        assert d["cas"] == "67-64-1"
        assert d["value"] == -17.8
        assert d["source"] == "PubChem"

    def test_evidence_from_dict(self):
        from packages.auto_p2oasys.evidence import Evidence

        d = {
            "cas": "67-64-1",
            "endpoint": "flash_point",
            "value": -17.8,
            "unit": "°C",
            "source": "PubChem",
        }
        ev = Evidence.from_dict(d)
        assert ev.cas == "67-64-1"
        assert ev.value == -17.8


class TestSourceReport:
    """Tests for SourceReport."""

    def test_source_report_add(self):
        from packages.auto_p2oasys.source_report import SourceReport, AdapterStatus

        report = SourceReport()
        report.add("pubchem", AdapterStatus.RAN, evidence_count=5)
        report.add("cameo", AdapterStatus.NO_DATA, "CAS not found")

        assert len(report.ran) == 1
        assert len(report.adapters) == 2
        assert report.total_evidence == 5

    def test_source_report_print_summary(self):
        from packages.auto_p2oasys.source_report import SourceReport, AdapterStatus

        report = SourceReport()
        report.cas = "67-64-1"
        report.mode = "fast"
        report.add("pubchem", AdapterStatus.RAN, evidence_count=5)

        summary = report.print_summary()
        assert "67-64-1" in summary
        assert "pubchem" in summary


class TestExpertLookup:
    """Tests for expert score lookup (offline)."""

    def test_expert_lookup_acetone(self):
        """Acceptance criterion 1: auto_p2oasys("67-64-1") returns mode expert."""
        from packages.auto_p2oasys import auto_p2oasys, P2OASysMode

        result = auto_p2oasys("67-64-1")

        assert result.mode == P2OASysMode.EXPERT
        assert result.cas == "67-64-1"
        assert result.overall is not None
        assert result.expert_overall is not None

    def test_expert_lookup_nonexistent(self):
        """CAS not in lookup should try fast pipeline (offline: returns not_found)."""
        from packages.auto_p2oasys import auto_p2oasys, P2OASysMode

        result = auto_p2oasys("9999-99-9")
        assert result.mode in (P2OASysMode.FAST, P2OASysMode.NOT_FOUND)


class TestForceFast:
    """Tests for force_fast mode."""

    def test_force_fast_returns_expert_plus_fast(self):
        """Acceptance criterion 2: force_fast returns expert+fast with trace."""
        from packages.auto_p2oasys import auto_p2oasys, P2OASysMode

        result = auto_p2oasys("67-64-1", force_fast=True)

        assert result.mode == P2OASysMode.EXPERT_PLUS_FAST
        assert result.expert_overall is not None
        assert result.source_report is not None
        assert len(result.source_report.adapters) > 0

    def test_force_fast_source_report_has_adapters(self):
        """Source report should show adapter status."""
        from packages.auto_p2oasys import auto_p2oasys

        result = auto_p2oasys("67-64-1", force_fast=True)
        report = result.source_report

        summary = report.print_summary()
        # Check that source report shows adapters (at least skipped/disabled ones)
        assert "opera" in summary.lower() or "ecosar" in summary.lower() or "hspip" in summary.lower()


class TestHazardBuilder:
    """Tests for HazardDataBuilder."""

    def test_build_hazard_data_from_evidence(self):
        from packages.auto_p2oasys.evidence import Evidence
        from packages.auto_p2oasys.hazard_builder import HazardDataBuilder

        builder = HazardDataBuilder("67-64-1")

        builder.add_evidence(
            Evidence(
                cas="67-64-1",
                endpoint="oral_ld50",
                value=5800,
                unit="mg/kg",
                source="PubChem",
            )
        )
        builder.add_evidence(
            Evidence(
                cas="67-64-1",
                endpoint="flash_point",
                value=-17.8,
                unit="°C",
                source="SDS",
            )
        )
        builder.add_evidence(
            Evidence(
                cas="67-64-1",
                endpoint="h_codes",
                value=["H225", "H319", "H336"],
                source="PubChem",
            )
        )

        hazard_data = builder.build()

        assert len(hazard_data["toxicities"]) > 0
        assert len(hazard_data["hazard_metrics"]["flash_point"]) > 0
        assert "H225" in hazard_data["ghs"]["h_codes"]


class TestGapFillLayer:
    """Tests for gap-fill layer."""

    def test_gapfill_measured_preferred(self):
        from packages.auto_p2oasys.evidence import Evidence
        from packages.auto_p2oasys.gapfill import GapFillLayer

        evidence = [
            Evidence(
                cas="67-64-1",
                endpoint="oral_ld50",
                value=5800,
                unit="mg/kg",
                source="PubChem",
                predicted=False,
            ),
            Evidence(
                cas="67-64-1",
                endpoint="oral_ld50",
                value=6000,
                unit="mg/kg",
                source="OPERA",
                predicted=True,
            ),
        ]

        layer = GapFillLayer(evidence)
        result = layer.fill("Oral Toxicity")

        assert result.predicted is False
        assert result.source == "PubChem"

    def test_gapfill_predicted_fallback(self):
        from packages.auto_p2oasys.evidence import Evidence
        from packages.auto_p2oasys.gapfill import GapFillLayer

        evidence = [
            Evidence(
                cas="67-64-1",
                endpoint="opera_bcf",
                value=3.2,
                unit="L/kg",
                source="OPERA",
                predicted=True,
            ),
        ]

        layer = GapFillLayer(evidence)
        result = layer.fill("Bioconcentration/ Bioaccumulation")

        assert result.predicted is True


class TestCapabilityReport:
    """Tests for capability report (adapter status)."""

    def test_capability_report_shows_all_adapters(self):
        """Acceptance criterion 5: Capability report shows every adapter with status."""
        from packages.auto_p2oasys import auto_p2oasys

        result = auto_p2oasys("67-64-1", force_fast=True)
        report = result.source_report

        adapter_names = [a.name for a in report.adapters]

        assert len(adapter_names) > 0

        assert any("hspip" in name.lower() for name in adapter_names) or \
               any("flash" in name.lower() for name in adapter_names)


class TestCLI:
    """Tests for CLI module."""

    def test_cli_version(self):
        from packages.auto_p2oasys.__main__ import main

        import io
        import sys

        old_stdout = sys.stdout
        sys.stdout = io.StringIO()

        try:
            exit_code = main(["--version"])
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout

        assert exit_code == 0
        assert "auto_p2oasys" in output

    def test_cli_cas_expert(self):
        from packages.auto_p2oasys.__main__ import main

        import io
        import sys

        old_stdout = sys.stdout
        sys.stdout = io.StringIO()

        try:
            exit_code = main(["--cas", "67-64-1", "--quiet"])
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout

        assert exit_code == 0
        assert "67-64-1" in output
        assert "expert" in output.lower()


class TestP2OASysResult:
    """Tests for P2OASysResult."""

    def test_result_to_dict(self):
        from packages.auto_p2oasys.core import P2OASysResult, P2OASysMode

        result = P2OASysResult(
            cas="67-64-1",
            mode=P2OASysMode.EXPERT,
            overall=4.5,
            expert_overall=4.5,
        )

        d = result.to_dict()
        assert d["cas"] == "67-64-1"
        assert d["mode"] == "expert"
        assert d["overall"] == 4.5

    def test_result_print_summary(self):
        from packages.auto_p2oasys.core import P2OASysResult, P2OASysMode

        result = P2OASysResult(
            cas="67-64-1",
            mode=P2OASysMode.EXPERT,
            overall=4.5,
        )

        summary = result.print_summary()
        assert "67-64-1" in summary
        assert "expert" in summary.lower()


class TestCAMEOAdapter:
    """Tests for CAMEO NFPA adapter."""

    def test_cameo_acetone_nfpa(self):
        """CAMEO adapter returns correct NFPA ratings for acetone."""
        from packages.auto_p2oasys.adapters.cameo import gather_nfpa, is_cameo_available

        if not is_cameo_available():
            pytest.skip("CAMEO database not available")

        evidence = gather_nfpa("67-64-1")
        endpoints = {ev.endpoint: ev.value for ev in evidence}

        assert endpoints.get("nfpa_health") == 1
        assert endpoints.get("nfpa_flam") == 3
        assert endpoints.get("nfpa_react") == 0

    def test_cameo_uses_correct_columns(self):
        """CAMEO uses nfpa_flam and nfpa_react (not nfpa_fire/nfpa_reactivity)."""
        from packages.auto_p2oasys.adapters.cameo import gather_nfpa, is_cameo_available

        if not is_cameo_available():
            pytest.skip("CAMEO database not available")

        evidence = gather_nfpa("67-64-1")
        endpoint_names = [ev.endpoint for ev in evidence]

        assert "nfpa_flam" in endpoint_names
        assert "nfpa_react" in endpoint_names
        assert "nfpa_fire" not in endpoint_names
        assert "nfpa_reactivity" not in endpoint_names


class TestIARCLookup:
    """Tests for IARC carcinogen lookup."""

    def test_iarc_benzene_group_1(self):
        """Benzene (71-43-2) should return IARC Group 1."""
        from packages.auto_p2oasys.adapters.lookup_tables import gather_iarc

        evidence = gather_iarc("71-43-2")
        assert len(evidence) == 1
        assert evidence[0].endpoint == "iarc"
        assert evidence[0].value == "1"
        assert evidence[0].source == "IARC"

    def test_iarc_uses_correct_column(self):
        """IARC uses 'iarc' column (not iarc_group)."""
        from packages.auto_p2oasys.adapters.lookup_tables import gather_iarc

        evidence = gather_iarc("71-43-2")
        assert len(evidence) == 1
        assert evidence[0].value == "1"


class TestIUCLIDAdapter:
    """Tests for IUCLID adapter with ECHA attribution."""

    def test_echa_attribution_constant(self):
        from packages.auto_p2oasys.adapters.iuclid import ECHA_ATTRIBUTION

        assert "ECHA" in ECHA_ATTRIBUTION
        assert "European Chemicals Agency" in ECHA_ATTRIBUTION

    def test_iuclid_endpoints_defined(self):
        from packages.auto_p2oasys.adapters.iuclid import IUCLID_ENDPOINTS

        assert "inhalation_lc50" in IUCLID_ENDPOINTS
        assert "repeated_dose_toxicity" in IUCLID_ENDPOINTS
        assert "genotoxicity_in_vitro" in IUCLID_ENDPOINTS
        assert "biodegradation" in IUCLID_ENDPOINTS
        assert "chronic_aquatic_noec" in IUCLID_ENDPOINTS


class TestCarcinogenLookup:
    """Tests for IARC + EPA carcinogen matching."""

    def test_iarc_cas_normalization(self):
        from packages.auto_p2oasys.cas_utils import normalize_cas

        assert normalize_cas("71-43-2") == "71432"
        assert normalize_cas("71432") == "71432"

    def test_epa_carcinogen_function_exists(self):
        from packages.auto_p2oasys.adapters.lookup_tables import gather_epa_carcinogen

        result = gather_epa_carcinogen("71-43-2")
        assert isinstance(result, list)


class TestOdorThreshold:
    """Tests for odor threshold lookup."""

    def test_odor_threshold_missing_flag(self):
        from packages.auto_p2oasys.adapters.lookup_tables import gather_odor_threshold

        result = gather_odor_threshold("99999-99-9")
        assert len(result) == 1
        assert result[0].source == "MISSING"


class TestNotWired:
    """Tests for NOT_WIRED endpoint markers."""

    def test_idlh_not_wired(self):
        from packages.auto_p2oasys.adapters.lookup_tables import gather_idlh

        result = gather_idlh("67-64-1")
        assert len(result) == 1
        assert result[0].source == "NOT_WIRED"
        assert result[0].endpoint == "idlh"

    def test_reportable_quantity_not_wired(self):
        from packages.auto_p2oasys.adapters.lookup_tables import gather_reportable_quantity

        result = gather_reportable_quantity("67-64-1")
        assert len(result) == 1
        assert result[0].source == "NOT_WIRED"
        assert result[0].endpoint == "reportable_quantity"


class TestFlashPointRouting:
    """Tests for flash point measured-first routing."""

    def test_flash_prediction_skips_when_measured(self):
        from packages.auto_p2oasys.adapters.predictions import gather_flash_prediction

        result = gather_flash_prediction("67-64-1", measured_available=True)
        assert result == []


def test_flash_predict_stub():
    """Test that flash point prediction interface exists (model not yet provided)."""
    from packages.auto_p2oasys.adapters.predictions import gather_flash_prediction

    result = gather_flash_prediction("67-64-1", measured_available=False)
    assert isinstance(result, list)


class TestFlashPointPredictor:
    """Tests for Maestri flash point predictor."""

    def test_model_not_configured_status(self):
        """When TURI_FPT_MODEL_DIR not set, status should be NOT_CONFIGURED."""
        import os
        
        old_val = os.environ.pop("TURI_FPT_MODEL_DIR", None)
        
        try:
            from packages.auto_p2oasys.adapters.predictions import FlashPointPredictor
            
            FlashPointPredictor._instance = None
            predictor = FlashPointPredictor.get_instance()
            
            status = predictor.get_status()
            assert status["available"] is False
            assert status["status"] == "NOT_CONFIGURED"
            assert "TURI_FPT_MODEL_DIR" in status.get("reason", "")
        finally:
            if old_val is not None:
                os.environ["TURI_FPT_MODEL_DIR"] = old_val

    def test_model_status_function(self):
        """get_flash_model_status returns valid status dict."""
        from packages.auto_p2oasys.adapters.predictions import get_flash_model_status
        
        status = get_flash_model_status()
        assert isinstance(status, dict)
        assert "available" in status
        assert "status" in status

    def test_flash_prediction_returns_list_when_unavailable(self):
        """gather_flash_prediction returns empty list when model unavailable."""
        import os
        
        old_val = os.environ.pop("TURI_FPT_MODEL_DIR", None)
        
        try:
            from packages.auto_p2oasys.adapters.predictions import gather_flash_prediction, FlashPointPredictor
            
            FlashPointPredictor._instance = None
            
            result = gather_flash_prediction("67-64-1", measured_available=False)
            assert result == []
        finally:
            if old_val is not None:
                os.environ["TURI_FPT_MODEL_DIR"] = old_val


class TestFPTPredict:
    """Tests for fpt_predict package."""

    def test_module_imports(self):
        """fpt_predict module imports successfully."""
        from packages import fpt_predict
        
        assert hasattr(fpt_predict, "predict")
        assert hasattr(fpt_predict, "is_available")
        assert hasattr(fpt_predict, "get_model_status")
        assert hasattr(fpt_predict, "FPTModelNotConfiguredError")

    def test_ad_module(self):
        """Applicability domain module works."""
        from packages.fpt_predict.ad import (
            check_applicability_domain,
            compute_ad_threshold,
            ApplicabilityDomainResult,
        )
        import numpy as np
        
        training = np.array([[1, 2], [2, 3], [3, 4], [4, 5], [5, 6], [6, 7]])
        query = np.array([3.5, 4.5])
        
        threshold = compute_ad_threshold(training)
        assert threshold > 0
        
        result = check_applicability_domain(query, training, threshold)
        assert isinstance(result, ApplicabilityDomainResult)
        assert isinstance(result.in_domain, bool)
        assert result.distance >= 0

    def test_ad_out_of_domain(self):
        """Applicability domain correctly identifies out-of-domain points."""
        from packages.fpt_predict.ad import check_applicability_domain
        import numpy as np
        
        training = np.array([[0, 0], [1, 1], [2, 2], [3, 3], [4, 4], [5, 5]])
        
        far_point = np.array([100, 100])
        threshold = 2.0
        
        result = check_applicability_domain(far_point, training, threshold)
        assert result.in_domain is False
        assert result.distance > threshold


class TestCompToxAdapter:
    """Tests for CompTox DSSTox and ToxValDB adapters."""

    def test_dsstox_availability_check(self):
        from packages.auto_p2oasys.adapters.comptox import is_dsstox_available

        result = is_dsstox_available()
        assert isinstance(result, bool)

    def test_toxvaldb_availability_check(self):
        from packages.auto_p2oasys.adapters.comptox import is_toxvaldb_available

        result = is_toxvaldb_available()
        assert isinstance(result, bool)

    def test_dsstox_gather_returns_list(self):
        from packages.auto_p2oasys.adapters.comptox import gather_dsstox

        result = gather_dsstox("67-64-1")
        assert isinstance(result, list)

    def test_toxvaldb_gather_returns_list(self):
        from packages.auto_p2oasys.adapters.comptox import gather_toxvaldb

        result = gather_toxvaldb("67-64-1")
        assert isinstance(result, list)


class TestCPDBAdapter:
    """Tests for CPDB carcinogenic potency adapter."""

    def test_cpdb_availability_check(self):
        from packages.auto_p2oasys.adapters.cpdb import is_cpdb_available

        result = is_cpdb_available()
        assert isinstance(result, bool)

    def test_cpdb_gather_returns_list(self):
        from packages.auto_p2oasys.adapters.cpdb import gather_cpdb

        result = gather_cpdb("71-43-2")
        assert isinstance(result, list)


class TestAtmosphericAdapter:
    """Tests for atmospheric hazard adapters."""

    def test_ipcc_availability_check(self):
        from packages.auto_p2oasys.adapters.atmospheric import is_ipcc_available

        result = is_ipcc_available()
        assert isinstance(result, bool)

    def test_ipcc_gwp_gather_returns_list(self):
        from packages.auto_p2oasys.adapters.atmospheric import gather_ipcc_gwp

        result = gather_ipcc_gwp("75-45-6")
        assert isinstance(result, list)

    def test_atmospheric_rules_defaults(self):
        from packages.auto_p2oasys.adapters.atmospheric import apply_atmospheric_rules

        hazard_data = {"hazard_metrics": {}}
        result = apply_atmospheric_rules("67-64-1", hazard_data)

        assert isinstance(result, list)
        assert len(result) >= 2
        endpoints = [ev.endpoint for ev in result]
        assert "gwp100" in endpoints or "odp" in endpoints

    def test_ph_cascade_experimental(self):
        from packages.auto_p2oasys.adapters.atmospheric import estimate_ph

        hazard_data = {"exp_ph_1pct": 5.5}
        result = estimate_ph("67-64-1", hazard_data)

        assert len(result) == 1
        assert result[0].endpoint == "ph_estimate"
        assert result[0].value == 5.5
        assert result[0].predicted is False

    def test_ph_cascade_pka(self):
        from packages.auto_p2oasys.adapters.atmospheric import estimate_ph

        hazard_data = {"pKa": 2.5}
        result = estimate_ph("64-19-7", hazard_data)

        assert len(result) == 1
        assert result[0].endpoint == "ph_estimate"
        assert result[0].predicted is True

    def test_ph_cascade_smarts(self):
        from packages.auto_p2oasys.adapters.atmospheric import estimate_ph

        hazard_data = {"smiles": "CC(=O)O"}
        result = estimate_ph("64-19-7", hazard_data)

        assert len(result) == 1
        assert result[0].endpoint == "ph_estimate"
        assert result[0].predicted is True


class TestHazardBuilderAttributions:
    """Tests for HazardDataBuilder attributions and special tracking."""

    def test_epa_carcinogen_added(self):
        from packages.auto_p2oasys.evidence import Evidence
        from packages.auto_p2oasys.hazard_builder import HazardDataBuilder

        builder = HazardDataBuilder("71-43-2")
        builder.add_evidence(
            Evidence(
                cas="71-43-2",
                endpoint="epa_carcinogen",
                value="A",
                source="EPA IRIS",
            )
        )

        hazard_data = builder.build()
        tox_values = [t["value"] for t in hazard_data["toxicities"]]
        assert any("EPA Carcinogen" in v for v in tox_values)

    def test_not_wired_tracked(self):
        from packages.auto_p2oasys.evidence import Evidence
        from packages.auto_p2oasys.hazard_builder import HazardDataBuilder

        builder = HazardDataBuilder("67-64-1")
        builder.add_evidence(
            Evidence(
                cas="67-64-1",
                endpoint="idlh",
                value=None,
                source="NOT_WIRED",
                reference="IDLH not implemented",
            )
        )

        hazard_data = builder.build()
        assert "not_wired_endpoints" in hazard_data
        assert "idlh" in hazard_data["not_wired_endpoints"]

    def test_iuclid_attribution_tracked(self):
        from packages.auto_p2oasys.evidence import Evidence
        from packages.auto_p2oasys.hazard_builder import HazardDataBuilder
        from packages.auto_p2oasys.adapters.iuclid import ECHA_ATTRIBUTION

        builder = HazardDataBuilder("71-43-2")
        builder.add_evidence(
            Evidence(
                cas="71-43-2",
                endpoint="inhalation_lc50",
                value=10.5,
                unit="mg/L",
                source=ECHA_ATTRIBUTION,
            )
        )

        hazard_data = builder.build()
        assert "iuclid_attribution" in hazard_data
        assert ECHA_ATTRIBUTION in hazard_data["iuclid_attribution"]
