"""Tests for P2OASys assess() automatic hazard assessment spine."""
from __future__ import annotations

from packages.p2oasys_core.assess import AssessmentResult, assess


KNOWN_EXPERT_CAS = "100-37-8"
KNOWN_CAS_ACETONE = "67-64-1"
UNKNOWN_CAS = "999999-99-9"


class TestAssessmentResultStructure:
    """AssessmentResult has correct structure with Auto6 only."""

    def test_assess_returns_assessment_result(self):
        result = assess(KNOWN_EXPERT_CAS)
        assert isinstance(result, AssessmentResult)

    def test_result_has_auto6_fields(self):
        result = assess(KNOWN_EXPERT_CAS)
        assert hasattr(result, "acute")
        assert hasattr(result, "chronic")
        assert hasattr(result, "ecological")
        assert hasattr(result, "fate")
        assert hasattr(result, "atmospheric")
        assert hasattr(result, "physical")

    def test_result_has_overall_and_source(self):
        result = assess(KNOWN_EXPERT_CAS)
        assert hasattr(result, "overall")
        assert hasattr(result, "source")

    def test_result_has_cas_and_name(self):
        result = assess(KNOWN_EXPERT_CAS)
        assert hasattr(result, "cas")
        assert hasattr(result, "name")

    def test_process_factors_not_in_result(self):
        """Process Factors must NOT be in AssessmentResult (human expert input required)."""
        result = assess(KNOWN_EXPERT_CAS)
        assert not hasattr(result, "process")
        assert not hasattr(result, "process_factors")
        assert not hasattr(result, "expert_process")

    def test_life_cycle_factors_not_in_result(self):
        """Life Cycle Factors must NOT be in AssessmentResult (human expert input required)."""
        result = assess(KNOWN_EXPERT_CAS)
        assert not hasattr(result, "life_cycle")
        assert not hasattr(result, "life_cycle_factors")
        assert not hasattr(result, "expert_life_cycle")


class TestExpertPrecedence:
    """Expert scores take precedence over auto scores."""

    def test_expert_source_for_known_expert_cas(self):
        result = assess(KNOWN_EXPERT_CAS)
        assert result.source == "expert"

    def test_expert_scores_returned_when_available(self):
        result = assess(KNOWN_EXPERT_CAS)
        assert result.source == "expert"
        assert result.overall is not None
        assert result.acute is not None


class TestMissingCAS:
    """Missing CAS returns appropriate not_found result."""

    def test_unknown_cas_returns_not_found_source(self):
        result = assess(UNKNOWN_CAS)
        assert result.source == "not_found"

    def test_unknown_cas_has_none_scores(self):
        result = assess(UNKNOWN_CAS)
        assert result.acute is None
        assert result.chronic is None
        assert result.ecological is None
        assert result.fate is None
        assert result.atmospheric is None
        assert result.physical is None
        assert result.overall is None

    def test_unknown_cas_preserves_input_cas(self):
        result = assess(UNKNOWN_CAS)
        assert "999999" in result.cas


class TestOverallCalculation:
    """Overall is max of Auto6 category scores."""

    def test_overall_is_max_of_auto6(self):
        result = assess(KNOWN_EXPERT_CAS)
        scores = [
            result.acute,
            result.chronic,
            result.ecological,
            result.fate,
            result.atmospheric,
            result.physical,
        ]
        non_none = [s for s in scores if s is not None]
        if non_none:
            expected_max = max(non_none)
            assert result.overall == expected_max


class TestCASNormalization:
    """CAS input is normalized correctly."""

    def test_cas_with_dashes(self):
        result = assess("100-37-8")
        assert result.source == "expert"
        assert result.cas == "100-37-8"

    def test_cas_without_dashes(self):
        result = assess("100378")
        assert result.source == "expert"
        assert result.cas == "100-37-8"

    def test_cas_with_spaces(self):
        result = assess(" 100-37-8 ")
        assert result.source == "expert"


class TestSDSDataParameter:
    """sds_data parameter is accepted (reserved for future use)."""

    def test_assess_accepts_sds_data_none(self):
        result = assess(KNOWN_EXPERT_CAS, sds_data=None)
        assert result.source == "expert"

    def test_assess_accepts_sds_data_dict(self):
        result = assess(KNOWN_EXPERT_CAS, sds_data={"placeholder": "data"})
        assert result.source == "expert"


class TestDataIntegrity:
    """Scores are never invented — real data from SQLite."""

    def test_scores_are_numeric_or_none(self):
        result = assess(KNOWN_EXPERT_CAS)
        for score in [
            result.acute,
            result.chronic,
            result.ecological,
            result.fate,
            result.atmospheric,
            result.physical,
            result.overall,
        ]:
            assert score is None or isinstance(score, (int, float))

    def test_scores_in_valid_range(self):
        result = assess(KNOWN_EXPERT_CAS)
        for score in [
            result.acute,
            result.chronic,
            result.ecological,
            result.fate,
            result.atmospheric,
            result.physical,
            result.overall,
        ]:
            if score is not None:
                assert 1 <= score <= 10, f"Score {score} out of range 1-10"

    def test_name_is_populated_for_known_cas(self):
        result = assess(KNOWN_EXPERT_CAS)
        assert result.name is not None
        assert len(result.name) > 0
