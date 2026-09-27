"""
Tests for P2OASys Process Factors & Life Cycle Factors survey.

Tests cover:
- Data model (SurveyAnswers, SubcategoryAnswer)
- Matrix definitions
- Save/load functionality
- CLI interface
- Streamlit component imports
- CRITICAL: Blank-stays-blank behavior (never default to 2)
"""

import json
import tempfile
from pathlib import Path

import pytest

from packages.p2oasys_core.survey import (
    BAND_SCORES,
    Category,
    LIFE_CYCLE_FACTORS_MATRIX,
    PROCESS_FACTORS_MATRIX,
    SubcategoryAnswer,
    SurveyAnswers,
    delete_survey,
    get_all_options,
    get_band_description,
    get_subcategories,
    list_saved_surveys,
    load_survey,
    save_survey,
    survey_file_path,
)


class TestMatrixDefinitions:
    """Test TURI matrix band definitions."""

    def test_process_factors_subcategories(self):
        """Process Factors has expected subcategories from TURI matrix."""
        subcats = get_subcategories(Category.PROCESS_FACTORS)
        assert len(subcats) == 10
        # From "Hazard Matrix Group Review 9-19-23.xlsx" Process Factors sheet
        assert "Heat" in subcats
        assert "Cold" in subcats
        assert "Noise" in subcats
        assert "Vibration" in subcats
        assert "Ergonomic Hazard" in subcats
        assert "Psychosocial Hazard" in subcats
        assert "High/Low Pressure System" in subcats
        assert "High/Low Temperature System" in subcats
        assert "Water Use" in subcats
        assert "Energy Use" in subcats

    def test_life_cycle_factors_subcategories(self):
        """Life Cycle Factors has expected subcategories from TURI matrix."""
        subcats = get_subcategories(Category.LIFE_CYCLE_FACTORS)
        assert len(subcats) == 5
        # From "Hazard Matrix Group Review 9-19-23.xlsx" Life Cycle Factors sheet
        assert "Upstream Effects" in subcats
        assert "Consumer Hazard" in subcats
        assert "Disposal Hazard" in subcats
        assert "Recycling" in subcats
        assert "Renewable to Nonrenewable Resource" in subcats

    def test_all_subcategories_have_band_descriptions(self):
        """Every subcategory must have descriptions for all band scores."""
        for category in Category:
            for subcategory in get_subcategories(category):
                for score in BAND_SCORES:
                    desc = get_band_description(category, subcategory, score)
                    assert desc is not None, f"Missing description for {category.value}/{subcategory} score {score}"
                    assert len(desc) > 10, f"Description too short for {category.value}/{subcategory} score {score}"

    def test_get_all_options(self):
        """get_all_options returns score-description pairs."""
        options = get_all_options(Category.PROCESS_FACTORS, "Heat")
        assert len(options) == 5
        scores = [o["score"] for o in options]
        assert scores == [2, 4, 6, 8, 10]
        for opt in options:
            assert "description" in opt
            assert len(opt["description"]) > 10

    def test_invalid_category_returns_empty(self):
        """Invalid category returns empty list/None."""
        # Pass a string instead of Category enum
        assert get_all_options("invalid", "test") == []


class TestSubcategoryAnswer:
    """Test SubcategoryAnswer data model."""

    def test_create_with_score(self):
        """Create answer with valid score."""
        answer = SubcategoryAnswer(
            category="Process Factors",
            subcategory="Heat",
            score=6,
        )
        assert answer.score == 6
        assert answer.source == "user"
        assert answer.is_answered is True

    def test_create_blank(self):
        """Create blank answer (score=None)."""
        answer = SubcategoryAnswer(
            category="Process Factors",
            subcategory="Heat",
            score=None,
        )
        assert answer.score is None
        assert answer.is_answered is False

    def test_invalid_score_raises(self):
        """Invalid score (not in 2,4,6,8,10) raises ValueError."""
        with pytest.raises(ValueError):
            SubcategoryAnswer(
                category="Process Factors",
                subcategory="Heat",
                score=5,  # Invalid: not in BAND_SCORES
            )

    def test_to_dict_from_dict_roundtrip(self):
        """Serialize and deserialize answer."""
        original = SubcategoryAnswer(
            category="Life Cycle Factors",
            subcategory="Disposal Hazard",
            score=8,
            note="Based on MSDS review",
            answered_at="2024-01-15T10:30:00",
        )
        data = original.to_dict()
        restored = SubcategoryAnswer.from_dict(data)
        assert restored.score == original.score
        assert restored.note == original.note
        assert restored.source == original.source


class TestSurveyAnswers:
    """Test SurveyAnswers data model."""

    def test_create_empty_survey(self):
        """Create survey with no answers."""
        survey = SurveyAnswers(cas="67-64-1")
        assert survey.cas == "67-64-1"
        assert survey.count_answered() == 0
        assert survey.count_total() == 15  # 10 Process + 5 Life Cycle subcategories

    def test_set_and_get_answer(self):
        """Set and retrieve answers."""
        survey = SurveyAnswers(cas="67-64-1")
        survey.set_answer(Category.PROCESS_FACTORS, "Heat", 4, "Low heat exposure")

        answer = survey.get_answer(Category.PROCESS_FACTORS, "Heat")
        assert answer is not None
        assert answer.score == 4
        assert answer.note == "Low heat exposure"
        assert answer.source == "user"

    def test_blank_stays_blank_never_default_to_2(self):
        """
        CRITICAL: Blank stays blank. Never auto-fill with score 2.
        
        This is the most important test — the requirement is that unanswered
        subcategories must remain None, never defaulting to the lowest score.
        """
        survey = SurveyAnswers(cas="67-64-1")

        # Without setting any answer, get_score must return None (not 2)
        for category in Category:
            for subcategory in get_subcategories(category):
                score = survey.get_score(category, subcategory)
                assert score is None, (
                    f"CRITICAL FAILURE: {category.value}/{subcategory} returned {score} "
                    f"instead of None. Blank must stay blank!"
                )

    def test_category_max_returns_none_when_no_answers(self):
        """
        CRITICAL: category_max returns None when no answers, not 2.
        """
        survey = SurveyAnswers(cas="67-64-1")
        
        # No answers set — max must be None
        assert survey.category_max(Category.PROCESS_FACTORS) is None
        assert survey.category_max(Category.LIFE_CYCLE_FACTORS) is None

    def test_category_max_with_partial_answers(self):
        """category_max uses only answered subcategories."""
        survey = SurveyAnswers(cas="67-64-1")
        survey.set_answer(Category.PROCESS_FACTORS, "Heat", 4)
        survey.set_answer(Category.PROCESS_FACTORS, "Ergonomic Hazard", 8)
        
        # Max should be 8 (not including blanks)
        assert survey.category_max(Category.PROCESS_FACTORS) == 8

    def test_category_mean_with_partial_answers(self):
        """category_mean averages only answered subcategories."""
        survey = SurveyAnswers(cas="67-64-1")
        survey.set_answer(Category.LIFE_CYCLE_FACTORS, "Disposal Hazard", 2)
        survey.set_answer(Category.LIFE_CYCLE_FACTORS, "Consumer Hazard", 6)
        
        # Mean of [2, 6] = 4.0
        assert survey.category_mean(Category.LIFE_CYCLE_FACTORS) == 4.0
        
        # Other category still None
        assert survey.category_mean(Category.PROCESS_FACTORS) is None

    def test_count_answered_by_category(self):
        """count_answered filters by category when provided."""
        survey = SurveyAnswers(cas="67-64-1")
        survey.set_answer(Category.PROCESS_FACTORS, "Heat", 4)
        survey.set_answer(Category.LIFE_CYCLE_FACTORS, "Disposal Hazard", 6)
        
        assert survey.count_answered() == 2
        assert survey.count_answered(Category.PROCESS_FACTORS) == 1
        assert survey.count_answered(Category.LIFE_CYCLE_FACTORS) == 1

    def test_set_blank_answer(self):
        """Setting score=None explicitly marks as blank."""
        survey = SurveyAnswers(cas="67-64-1")
        survey.set_answer(Category.PROCESS_FACTORS, "Heat", 6)
        
        # Now clear it
        survey.set_answer(Category.PROCESS_FACTORS, "Heat", None)
        
        answer = survey.get_answer(Category.PROCESS_FACTORS, "Heat")
        assert answer is not None  # Answer object exists
        assert answer.score is None  # But score is blank
        assert answer.is_answered is False

    def test_to_dict_from_dict_roundtrip(self):
        """Full survey serialization roundtrip."""
        survey = SurveyAnswers(cas="67-64-1", chemical_name="Acetone")
        survey.set_answer(Category.PROCESS_FACTORS, "Heat", 4, "Note 1")
        survey.set_answer(Category.LIFE_CYCLE_FACTORS, "Disposal Hazard", 2, "Note 2")
        
        data = survey.to_dict()
        restored = SurveyAnswers.from_dict(data)
        
        assert restored.cas == survey.cas
        assert restored.chemical_name == survey.chemical_name
        assert restored.count_answered() == 2
        assert restored.get_score(Category.PROCESS_FACTORS, "Heat") == 4

    def test_summary(self):
        """summary() returns expected structure."""
        survey = SurveyAnswers(cas="67-64-1", chemical_name="Acetone")
        survey.set_answer(Category.PROCESS_FACTORS, "Heat", 4)
        survey.set_answer(Category.PROCESS_FACTORS, "Water Use", 6)
        
        summary = survey.summary()
        assert summary["cas"] == "67-64-1"
        assert summary["chemical_name"] == "Acetone"
        assert summary["process_factors"]["answered"] == 2
        assert summary["process_factors"]["total"] == 10
        assert summary["process_factors"]["max"] == 6
        assert summary["life_cycle_factors"]["max"] is None


class TestSaveLoadSurvey:
    """Test survey persistence (save/load per CAS)."""

    def test_save_and_load(self, tmp_path, monkeypatch):
        """Save survey and load it back."""
        monkeypatch.setenv("SURVEY_ANSWERS_DIR", str(tmp_path))
        
        survey = SurveyAnswers(cas="67-64-1", chemical_name="Acetone")
        survey.set_answer(Category.PROCESS_FACTORS, "Heat", 4)
        
        path = save_survey(survey)
        assert path.exists()
        
        loaded = load_survey("67-64-1")
        assert loaded is not None
        assert loaded.cas == "67-64-1"
        assert loaded.get_score(Category.PROCESS_FACTORS, "Heat") == 4

    def test_load_nonexistent_returns_none(self, tmp_path, monkeypatch):
        """Loading non-existent survey returns None."""
        monkeypatch.setenv("SURVEY_ANSWERS_DIR", str(tmp_path))
        
        result = load_survey("99999-99-9")
        assert result is None

    def test_list_saved_surveys(self, tmp_path, monkeypatch):
        """List all saved surveys."""
        monkeypatch.setenv("SURVEY_ANSWERS_DIR", str(tmp_path))
        
        # Save two surveys
        s1 = SurveyAnswers(cas="67-64-1", chemical_name="Acetone")
        s1.set_answer(Category.PROCESS_FACTORS, "Heat", 4)
        save_survey(s1)
        
        s2 = SurveyAnswers(cas="64-17-5", chemical_name="Ethanol")
        s2.set_answer(Category.LIFE_CYCLE_FACTORS, "Disposal Hazard", 2)
        save_survey(s2)
        
        surveys = list_saved_surveys()
        assert len(surveys) == 2
        cas_list = [s["cas"] for s in surveys]
        assert "67-64-1" in cas_list
        assert "64-17-5" in cas_list

    def test_delete_survey(self, tmp_path, monkeypatch):
        """Delete a saved survey."""
        monkeypatch.setenv("SURVEY_ANSWERS_DIR", str(tmp_path))
        
        survey = SurveyAnswers(cas="67-64-1")
        save_survey(survey)
        
        assert load_survey("67-64-1") is not None
        
        result = delete_survey("67-64-1")
        assert result is True
        
        assert load_survey("67-64-1") is None

    def test_survey_file_path_normalizes_cas(self, tmp_path, monkeypatch):
        """File path uses normalized CAS (digits only)."""
        monkeypatch.setenv("SURVEY_ANSWERS_DIR", str(tmp_path))
        
        path1 = survey_file_path("67-64-1")
        path2 = survey_file_path("67641")
        
        assert path1 == path2
        assert "67641" in path1.name


class TestSurveyDataModel:
    """Test capability: survey data model works correctly."""

    def test_survey_data_model(self):
        """Capability test: basic data model operations."""
        # Create survey
        survey = SurveyAnswers(cas="67-64-1")
        
        # Verify blank-by-default
        assert survey.count_answered() == 0
        for cat in Category:
            assert survey.category_max(cat) is None
        
        # Set some answers
        survey.set_answer(Category.PROCESS_FACTORS, "Heat", 6)
        assert survey.count_answered() == 1
        assert survey.get_score(Category.PROCESS_FACTORS, "Heat") == 6
        
        # Verify serialization
        data = survey.to_dict()
        assert "cas" in data
        assert "answers" in data
        
        # Verify deserialization
        restored = SurveyAnswers.from_dict(data)
        assert restored.get_score(Category.PROCESS_FACTORS, "Heat") == 6


class TestStreamlitSurveyImports:
    """Test capability: Streamlit survey page imports work."""

    def test_streamlit_survey_imports(self):
        """Capability test: survey page module imports without error."""
        # This tests that the module can be imported (dependencies available)
        from apps.doss_ondemand.survey_page import (
            render_survey_page,
            render_combined_results,
            render_survey_summary,
        )
        
        # Functions exist
        assert callable(render_survey_page)
        assert callable(render_combined_results)
        assert callable(render_survey_summary)


class TestCLIInterface:
    """Test CLI interface functions."""

    def test_cli_show_survey_form(self, capsys):
        """CLI show command outputs expected content."""
        from packages.p2oasys_core.survey import cli_show_survey_form
        
        cli_show_survey_form("67-64-1")
        
        captured = capsys.readouterr()
        assert "P2OASys Survey" in captured.out
        assert "67-64-1" in captured.out
        assert "Process Factors" in captured.out
        assert "Life Cycle Factors" in captured.out

    def test_cli_set_answer(self, tmp_path, monkeypatch, capsys):
        """CLI answer command saves correctly."""
        from packages.p2oasys_core.survey import cli_set_answer
        
        monkeypatch.setenv("SURVEY_ANSWERS_DIR", str(tmp_path))
        
        cli_set_answer(
            cas="67-64-1",
            category_name="Process Factors",
            subcategory="Heat",
            score_str="6",
            note="Test note",
        )
        
        captured = capsys.readouterr()
        assert "Answer saved" in captured.out
        
        # Verify it was saved
        loaded = load_survey("67-64-1")
        assert loaded is not None
        assert loaded.get_score(Category.PROCESS_FACTORS, "Heat") == 6

    def test_cli_set_blank_answer(self, tmp_path, monkeypatch, capsys):
        """CLI can set blank answer."""
        from packages.p2oasys_core.survey import cli_set_answer
        
        monkeypatch.setenv("SURVEY_ANSWERS_DIR", str(tmp_path))
        
        # First set a score
        cli_set_answer("67-64-1", "Process Factors", "Heat", "6")
        
        # Then clear it
        cli_set_answer("67-64-1", "Process Factors", "Heat", "blank")
        
        captured = capsys.readouterr()
        assert "blank" in captured.out
        
        loaded = load_survey("67-64-1")
        assert loaded.get_score(Category.PROCESS_FACTORS, "Heat") is None

    def test_cli_invalid_category(self, capsys):
        """CLI rejects invalid category."""
        from packages.p2oasys_core.survey import cli_set_answer
        
        cli_set_answer("67-64-1", "Invalid Category", "Test", "6")
        
        captured = capsys.readouterr()
        assert "Error" in captured.out
        assert "Unknown category" in captured.out

    def test_cli_invalid_score(self, capsys):
        """CLI rejects invalid score."""
        from packages.p2oasys_core.survey import cli_set_answer
        
        cli_set_answer("67-64-1", "Process Factors", "Heat", "5")  # 5 is invalid
        
        captured = capsys.readouterr()
        assert "Error" in captured.out
        assert "Invalid score" in captured.out


class TestIntegrationWithLookup:
    """Test integration with p2oasys_core.lookup module."""

    def test_survey_separate_from_auto6(self):
        """
        Survey answers are SEPARATE from Auto6 scoring.
        
        The overall P2OASys score from lookup.py is the max of Auto6 categories:
        Acute, Chronic, Ecological, Fate, Atmospheric, Physical
        
        Process Factors and Life Cycle Factors are NOT included in Auto6.
        """
        from packages.p2oasys_core.lookup import AUTO6_MAX_COLS
        
        # Verify Auto6 columns don't include Process or Life Cycle
        for col in AUTO6_MAX_COLS:
            assert "Process" not in col
            assert "Life" not in col
            assert "Cycle" not in col
