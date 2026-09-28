"""
Tests for SDS offline parse functionality.

Tests structured SDS parsing, bridge to Evidence, cache lookup,
and scorer integration per PR #12 brief.
"""
from __future__ import annotations

import os
import re
import pytest
from pathlib import Path

from tests.fixtures.synthetic_sds import write_text_pdf, SYNTH_PURE, SYNTH_MIX, SYNTH_ESTIMATED


class TestSDSTextParse:
    """Test text-level parsing from SYNTH_PURE via bridge's flattened fields."""

    def test_section_2_h_codes(self):
        """Parse H-codes from section 2."""
        from packages.auto_p2oasys.adapters import sds_text, sds_structured, sds_bridge
        
        sections = sds_text.split_sections(SYNTH_PURE)
        structured = sds_structured.parse_structured_sds(sections, full_text=SYNTH_PURE)
        fields = sds_bridge.structured_sds_to_extra_fields(structured)
        
        h_codes = fields.get("ghs_h_codes", [])
        assert "H225" in h_codes
        assert "H319" in h_codes
        assert "H336" in h_codes
        assert "H412" in h_codes

    def test_nfpa_ratings(self):
        """Parse NFPA Health, Fire, and Instability."""
        from packages.auto_p2oasys.adapters import sds_text, sds_structured, sds_bridge
        
        sections = sds_text.split_sections(SYNTH_PURE)
        structured = sds_structured.parse_structured_sds(sections, full_text=SYNTH_PURE)
        fields = sds_bridge.structured_sds_to_extra_fields(structured)
        
        assert fields.get("nfpa_health") == 2, f"Expected NFPA Health 2, got {fields.get('nfpa_health')}"
        assert fields.get("nfpa_fire") == 3, f"Expected NFPA Fire 3, got {fields.get('nfpa_fire')}"
        assert fields.get("nfpa_instability") == 0, f"Expected NFPA Instability 0, got {fields.get('nfpa_instability')}"

    def test_section_9_flash_point(self):
        """Parse flash point from section 9."""
        from packages.auto_p2oasys.adapters import sds_text, sds_structured, sds_bridge
        
        sections = sds_text.split_sections(SYNTH_PURE)
        structured = sds_structured.parse_structured_sds(sections, full_text=SYNTH_PURE)
        fields = sds_bridge.structured_sds_to_extra_fields(structured)
        
        fps = fields.get("flash_points", [])
        assert len(fps) > 0, "Flash point not parsed"
        assert fps[0].get("value_c") == -18, f"Expected -18, got {fps[0].get('value_c')}"

    def test_section_9_vapor_pressure(self):
        """Parse vapor pressure from section 9."""
        from packages.auto_p2oasys.adapters import sds_text, sds_structured, sds_bridge
        
        sections = sds_text.split_sections(SYNTH_PURE)
        structured = sds_structured.parse_structured_sds(sections, full_text=SYNTH_PURE)
        fields = sds_bridge.structured_sds_to_extra_fields(structured)
        
        vps = fields.get("vapor_pressures", [])
        assert len(vps) > 0, "Vapor pressure not parsed"
        vp = vps[0].get("value_mmhg")
        assert abs(vp - 184) < 1, f"Expected ~184, got {vp}"

    def test_section_9_ph(self):
        """Parse pH from section 9."""
        from packages.auto_p2oasys.adapters import sds_text, sds_structured, sds_bridge
        
        sections = sds_text.split_sections(SYNTH_PURE)
        structured = sds_structured.parse_structured_sds(sections, full_text=SYNTH_PURE)
        fields = sds_bridge.structured_sds_to_extra_fields(structured)
        
        ph = fields.get("ph")
        assert ph is not None, "pH not parsed"
        assert abs(float(ph) - 7.0) < 0.1, f"Expected ~7.0, got {ph}"

    def test_section_9_odor(self):
        """Parse odor descriptor from section 9."""
        from packages.auto_p2oasys.adapters import sds_text, sds_structured, sds_bridge
        
        sections = sds_text.split_sections(SYNTH_PURE)
        structured = sds_structured.parse_structured_sds(sections, full_text=SYNTH_PURE)
        fields = sds_bridge.structured_sds_to_extra_fields(structured)
        
        odor = fields.get("odor")
        assert odor is not None, "Odor not parsed"
        assert "pungent" in odor.lower() or "fruity" in odor.lower()

    def test_section_11_oral_ld50(self):
        """Parse oral LD50 from section 11 (bug fix 1: not confused with dermal)."""
        from packages.auto_p2oasys.adapters import sds_text, sds_structured, sds_bridge
        
        sections = sds_text.split_sections(SYNTH_PURE)
        structured = sds_structured.parse_structured_sds(sections, full_text=SYNTH_PURE)
        fields = sds_bridge.structured_sds_to_extra_fields(structured)
        
        oral_ld50 = fields.get("ld50_oral_mg_kg")
        dermal_ld50 = fields.get("ld50_dermal_mg_kg")
        
        assert oral_ld50 == 5800, f"Expected oral 5800, got {oral_ld50}"
        assert dermal_ld50 == 20000, f"Expected dermal 20000, got {dermal_ld50}"

    def test_section_11_inhalation_lc50(self):
        """Parse inhalation LC50 (bug fix 4: not deduplicated with aquatic)."""
        from packages.auto_p2oasys.adapters import sds_text, sds_structured, sds_bridge
        
        sections = sds_text.split_sections(SYNTH_PURE)
        structured = sds_structured.parse_structured_sds(sections, full_text=SYNTH_PURE)
        fields = sds_bridge.structured_sds_to_extra_fields(structured)
        
        inh_lc50 = fields.get("lc50_inhalation_ppm")
        assert inh_lc50 == 50100, f"Expected 50100, got {inh_lc50}"

    def test_section_12_aquatic_fish_lc50(self):
        """Parse aquatic fish LC50 with species (bug fix 5)."""
        from packages.auto_p2oasys.adapters import sds_text, sds_structured, sds_bridge
        
        sections = sds_text.split_sections(SYNTH_PURE)
        structured = sds_structured.parse_structured_sds(sections, full_text=SYNTH_PURE)
        fields = sds_bridge.structured_sds_to_extra_fields(structured)
        
        aq_all = fields.get("aquatic_toxicity_all", [])
        fish_hits = [a for a in aq_all if a.get("species") == "Fish"]
        assert len(fish_hits) > 0, "Fish LC50 not parsed"
        fish_lc50 = fish_hits[0].get("value")
        assert fish_lc50 == 5540 or abs(fish_lc50 - 5540) < 1

    def test_section_12_aquatic_noec(self):
        """Parse aquatic NOEC (bug fix 6)."""
        from packages.auto_p2oasys.adapters import sds_text, sds_structured, sds_bridge
        
        sections = sds_text.split_sections(SYNTH_PURE)
        structured = sds_structured.parse_structured_sds(sections, full_text=SYNTH_PURE)
        fields = sds_bridge.structured_sds_to_extra_fields(structured)
        
        noec = fields.get("chronic_noec_mg_l")
        assert noec is not None, "NOEC not parsed"
        assert noec == 2212 or abs(noec - 2212) < 1

    def test_section_12_bcf(self):
        """Parse BCF from section 12."""
        from packages.auto_p2oasys.adapters import sds_text, sds_structured, sds_bridge
        
        sections = sds_text.split_sections(SYNTH_PURE)
        structured = sds_structured.parse_structured_sds(sections, full_text=SYNTH_PURE)
        fields = sds_bridge.structured_sds_to_extra_fields(structured)
        
        bcf = fields.get("bcf")
        assert bcf is not None, "BCF not parsed"
        assert abs(float(bcf) - 0.69) < 0.1

    def test_section_14_transport_class(self):
        """Parse UN number and class from section 14."""
        from packages.auto_p2oasys.adapters import sds_text, sds_structured
        
        sections = sds_text.split_sections(SYNTH_PURE)
        structured = sds_structured.parse_structured_sds(sections, full_text=SYNTH_PURE)
        
        sec14 = structured.get("section_14", {})
        un_number = sec14.get("un_number")
        
        assert un_number == "1090" or un_number == 1090


class TestSDSPDFRoundTrip:
    """Test PDF round-trip with pypdf."""

    @pytest.fixture
    def synth_pure_pdf(self, tmp_path):
        """Write SYNTH_PURE to a PDF."""
        pytest.importorskip("pypdf")
        pdf_path = tmp_path / "synth_pure.pdf"
        lines = SYNTH_PURE.strip().split("\n")
        write_text_pdf(pdf_path, lines)
        return pdf_path

    def test_pdf_parse_extracts_cas(self, synth_pure_pdf):
        """parse_sds() from PDF extracts CAS."""
        from packages.auto_p2oasys.adapters.sds import extract_cas_from_sds
        
        cas_list = extract_cas_from_sds(synth_pure_pdf)
        assert "67-64-1" in cas_list

    def test_pdf_parse_returns_evidence(self, synth_pure_pdf):
        """parse_sds() from PDF returns Evidence list."""
        from packages.auto_p2oasys.adapters.sds import parse_sds
        
        evidence = parse_sds(synth_pure_pdf, "67-64-1")
        assert len(evidence) > 0, "No evidence extracted from PDF"
        
        endpoints = {ev.endpoint for ev in evidence}
        assert "h_codes" in endpoints or any("ld50" in ep.lower() for ep in endpoints)


class TestSDSBridge:
    """Test bridge from structured SDS to Evidence."""

    def test_evidence_has_source_type_sds(self):
        """Every Evidence from SDS has source_type='SDS'."""
        from packages.auto_p2oasys.adapters import sds_text, sds_structured, sds_bridge
        
        sections = sds_text.split_sections(SYNTH_PURE)
        structured = sds_structured.parse_structured_sds(sections, full_text=SYNTH_PURE)
        fields = sds_bridge.structured_sds_to_extra_fields(structured)
        
        evidence, unmapped = sds_bridge.sds_fields_to_evidence(
            fields,
            "67-64-1",
            source_label="SDS (Example Test Vendor (fictional), test.pdf)",
            vendor="Example Test Vendor (fictional)",
            revision="2024-01-01",
            file_name="test.pdf",
        )
        
        for ev in evidence:
            assert ev.source_type == "SDS", f"Evidence {ev.endpoint} has source_type={ev.source_type}"

    def test_evidence_source_has_vendor(self):
        """Evidence source string includes vendor name."""
        from packages.auto_p2oasys.adapters import sds_text, sds_structured, sds_bridge
        
        sections = sds_text.split_sections(SYNTH_PURE)
        structured = sds_structured.parse_structured_sds(sections, full_text=SYNTH_PURE)
        fields = sds_bridge.structured_sds_to_extra_fields(structured)
        
        evidence, _ = sds_bridge.sds_fields_to_evidence(
            fields,
            "67-64-1",
            source_label="SDS (Example Test Vendor (fictional), test.pdf)",
            vendor="Example Test Vendor (fictional)",
            revision="",
            file_name="test.pdf",
        )
        
        for ev in evidence:
            assert "Example Test Vendor" in ev.source or "SDS" in ev.source


class TestSDSLabels:
    """Test evidence reliability and predicted labels."""

    def test_measured_values_not_predicted(self):
        """Measured SDS values have predicted=False."""
        from packages.auto_p2oasys.adapters import sds_text, sds_structured, sds_bridge
        
        sections = sds_text.split_sections(SYNTH_PURE)
        structured = sds_structured.parse_structured_sds(sections, full_text=SYNTH_PURE)
        fields = sds_bridge.structured_sds_to_extra_fields(structured)
        
        evidence, _ = sds_bridge.sds_fields_to_evidence(
            fields,
            "67-64-1",
            source_label="SDS (test)",
            vendor="test",
            revision="",
            file_name="test.pdf",
        )
        
        ld50_ev = [ev for ev in evidence if "ld50" in ev.endpoint.lower()]
        for ev in ld50_ev:
            assert ev.predicted is False, f"LD50 {ev.endpoint} should not be predicted"

    def test_estimated_values_are_predicted(self):
        """Values with 'estimated'/'QSAR'/'ECOSAR' are predicted=True (bug fix 8)."""
        from packages.auto_p2oasys.adapters import sds_text, sds_structured, sds_bridge
        
        sections = sds_text.split_sections(SYNTH_ESTIMATED)
        structured = sds_structured.parse_structured_sds(sections, full_text=SYNTH_ESTIMATED)
        fields = sds_bridge.structured_sds_to_extra_fields(structured)
        
        evidence, _ = sds_bridge.sds_fields_to_evidence(
            fields,
            "12345-67-8",
            source_label="SDS (test)",
            vendor="test",
            revision="",
            file_name="test.pdf",
        )
        
        aquatic_ev = [ev for ev in evidence if "aquatic" in ev.endpoint.lower() or "lc50" in ev.endpoint.lower()]
        if aquatic_ev:
            assert any(ev.predicted for ev in aquatic_ev), "Estimated aquatic values should be predicted"


class TestSDSMixture:
    """Test mixture/solution detection and holdout."""

    def test_mixture_detected(self):
        """SYNTH_MIX sets mixture flag."""
        from packages.auto_p2oasys.adapters.sds import parse_sds_document
        
        from io import StringIO
        import tempfile
        
        pytest.importorskip("pypdf")
        
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "mix.pdf"
            lines = SYNTH_MIX.strip().split("\n")
            write_text_pdf(pdf_path, lines)
            
            outcome = parse_sds_document(pdf_path, "50-00-0")
            
            assert outcome.mixture is not None, "Mixture not detected"
            assert outcome.mixture.get("is_mixture") is True

    def test_pure_substance_not_mixture(self):
        """SYNTH_PURE does not set mixture flag."""
        from packages.auto_p2oasys.adapters.sds import parse_sds_document
        
        pytest.importorskip("pypdf")
        
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "pure.pdf"
            lines = SYNTH_PURE.strip().split("\n")
            write_text_pdf(pdf_path, lines)
            
            outcome = parse_sds_document(pdf_path, "67-64-1")
            
            assert outcome.mixture is None or outcome.mixture.get("is_mixture") is False


class TestSDSCache:
    """Test offline cache lookup."""

    def test_cache_lookup_picks_newest(self, tmp_path):
        """Cache lookup picks newest revision deterministically."""
        pytest.importorskip("pypdf")
        
        from packages.auto_p2oasys.adapters import sds_cache
        
        vendor_a = tmp_path / "67-64-1" / "VendorA" / "10_07_2024" / "aaaaaaaaaaaa"
        vendor_a.mkdir(parents=True)
        lines = SYNTH_PURE.strip().split("\n")
        write_text_pdf(vendor_a / "original.pdf", lines)
        
        vendor_b = tmp_path / "67641" / "VendorB" / "01_15_2025" / "bbbbbbbbbbbb"
        vendor_b.mkdir(parents=True)
        write_text_pdf(vendor_b / "original.pdf", lines)
        (vendor_b / "metadata.json").write_text('{"revision": "01/15/2025"}')
        
        hit = sds_cache.lookup_sds_in_cache("67-64-1", tmp_path)
        
        assert hit is not None, "Cache lookup failed"
        assert hit["vendor"] == "VendorB", f"Expected VendorB (newer), got {hit['vendor']}"

    def test_cache_miss_returns_none(self, tmp_path):
        """Unknown CAS returns None."""
        from packages.auto_p2oasys.adapters import sds_cache
        
        hit = sds_cache.lookup_sds_in_cache("99999-99-9", tmp_path)
        assert hit is None


class TestSDSNoSupplied:
    """Test no-SDS source report line."""

    def test_no_sds_report_line(self):
        """auto_p2oasys without SDS reports 'SDS: none supplied'."""
        from packages.auto_p2oasys.pipeline import gather_evidence
        from packages.auto_p2oasys.source_report import SourceReport
        
        report = SourceReport()
        gather_evidence("67-64-1", report=report)
        
        adapter_names = {a.name for a in report.adapters}
        assert "sds_parse" in adapter_names, "sds_parse not in report"
        
        sds_entry = next((a for a in report.adapters if a.name == "sds_parse"), None)
        assert sds_entry is not None
        assert sds_entry.reason is not None
        assert "none supplied" in sds_entry.reason.lower()


class TestHazardBuilderFixes:
    """Test hazard_builder bug fixes."""

    def test_noec_stays_chronic(self):
        """Bug A: NOEC routes to chronic_aquatic_noec, not aquatic_lc50."""
        from packages.auto_p2oasys.hazard_builder import HazardDataBuilder
        from packages.auto_p2oasys.evidence import Evidence
        
        builder = HazardDataBuilder("67-64-1")
        ev = Evidence(
            cas="67-64-1",
            endpoint="chronic_aquatic_noec",
            value=2212,
            unit="mg/L",
            source="SDS",
        )
        builder.add_evidence(ev)
        
        assert len(builder.chronic_aquatic_noec) == 1
        assert len(builder.aquatic_lc50) == 0

    def test_nfpa_flam_gets_fire_label(self):
        """Bug B: nfpa_flam endpoint gets 'Fire' label."""
        from packages.auto_p2oasys.hazard_builder import HazardDataBuilder
        from packages.auto_p2oasys.evidence import Evidence
        
        builder = HazardDataBuilder("67-64-1")
        ev = Evidence(
            cas="67-64-1",
            endpoint="nfpa_flam",
            value=3,
            source="CAMEO",
        )
        builder.add_evidence(ev)
        
        assert len(builder.nfpa) == 1
        assert "Fire" in builder.nfpa[0]

    def test_nfpa_react_gets_reactivity_label(self):
        """Bug B: nfpa_react endpoint gets 'Reactivity' label."""
        from packages.auto_p2oasys.hazard_builder import HazardDataBuilder
        from packages.auto_p2oasys.evidence import Evidence
        
        builder = HazardDataBuilder("67-64-1")
        ev = Evidence(
            cas="67-64-1",
            endpoint="nfpa_react",
            value=0,
            source="CAMEO",
        )
        builder.add_evidence(ev)
        
        assert len(builder.nfpa) == 1
        assert "Reactivity" in builder.nfpa[0]

    def test_aquatic_species_preserved(self):
        """Bug C: Aquatic values use actual species, not just 'fish'."""
        from packages.auto_p2oasys.hazard_builder import HazardDataBuilder
        from packages.auto_p2oasys.evidence import Evidence
        
        builder = HazardDataBuilder("67-64-1")
        builder.add_evidence(Evidence(
            cas="67-64-1",
            endpoint="ec50_daphnia",
            value=8800,
            unit="mg/L",
            source="SDS",
        ))
        builder.add_evidence(Evidence(
            cas="67-64-1",
            endpoint="lc50_fish",
            value=5540,
            unit="mg/L",
            source="SDS",
        ))
        
        hd = builder.build()
        tox_values = [t["value"] for t in hd["toxicities"]]
        
        daphnia_found = any("daphnia" in v.lower() for v in tox_values)
        fish_found = any("fish" in v.lower() for v in tox_values)
        
        assert daphnia_found, "Daphnia species not preserved"
        assert fish_found, "Fish species not preserved"

    def test_unmapped_evidence_collected(self):
        """Bug D: Unknown endpoints go to unmapped_evidence."""
        from packages.auto_p2oasys.hazard_builder import HazardDataBuilder
        from packages.auto_p2oasys.evidence import Evidence
        
        builder = HazardDataBuilder("67-64-1")
        ev = Evidence(
            cas="67-64-1",
            endpoint="some_unknown_endpoint",
            value="test value",
            source="SDS",
        )
        builder.add_evidence(ev)
        
        hd = builder.build()
        assert "unmapped_evidence" in hd
        assert len(hd["unmapped_evidence"]) > 0

    def test_ph_routes_to_experimental_ph(self):
        """Bug D: pH evidence routes to experimental_ph."""
        from packages.auto_p2oasys.hazard_builder import HazardDataBuilder
        from packages.auto_p2oasys.evidence import Evidence
        
        builder = HazardDataBuilder("67-64-1")
        ev = Evidence(
            cas="67-64-1",
            endpoint="ph",
            value=7.0,
            source="SDS",
            raw_text="pH: 7.0 (10 g/L, 20 C)",
        )
        builder.add_evidence(ev)
        
        hd = builder.build()
        assert "experimental_ph" in hd
        assert len(hd["experimental_ph"]) > 0


class TestOdorNormalization:
    """Test odor descriptor normalization."""

    def test_pungent_normalizes(self):
        """'Pungent, fruity' normalizes to 'Pungent or irritating odor'."""
        from packages.auto_p2oasys.hazard_builder import HazardDataBuilder
        from packages.auto_p2oasys.evidence import Evidence
        
        builder = HazardDataBuilder("67-64-1")
        ev = Evidence(
            cas="67-64-1",
            endpoint="odor",
            value="Pungent, fruity",
            source="SDS",
        )
        builder.add_evidence(ev)
        
        assert len(builder.sds_phrases) == 1
        assert builder.sds_phrases[0] == "Pungent or irritating odor"

    def test_odorless_normalizes(self):
        """'Odorless' normalizes correctly."""
        from packages.auto_p2oasys.hazard_builder import HazardDataBuilder
        from packages.auto_p2oasys.evidence import Evidence
        
        builder = HazardDataBuilder("67-64-1")
        ev = Evidence(
            cas="67-64-1",
            endpoint="odor",
            value="Odorless",
            source="SDS",
        )
        builder.add_evidence(ev)
        
        assert "Odorless" in builder.sds_phrases


class TestECOSARMeasuredWins:
    """Test ECOSAR gap-fill rule with SDS data."""

    def test_sds_lc50_blocks_ecosar(self):
        """SDS measured LC50 prevents ECOSAR gap-fill."""
        from packages.p2oasys_scorer.utils.p2oasys_scorer import _has_measured_aquatic_data
        
        hazard_data = {
            "toxicities": [
                {"value": "LC50 fish 5540 mg/L", "source": "SDS", "predicted": False},
            ],
            "ghs": {"h_codes": []},
        }
        
        has_measured = _has_measured_aquatic_data(hazard_data)
        assert has_measured is True

    def test_sds_h412_blocks_ecosar(self):
        """SDS H412 (chronic aquatic) blocks ECOSAR."""
        from packages.p2oasys_scorer.utils.p2oasys_scorer import _has_measured_aquatic_data
        
        hazard_data = {
            "toxicities": [],
            "ghs": {"h_codes": ["H412"]},
        }
        
        has_measured = _has_measured_aquatic_data(hazard_data)
        assert has_measured is True
