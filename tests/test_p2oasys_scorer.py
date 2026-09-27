"""
Tests for the P2OASys scorer package.

Ported from GHaz8 packages/ghaz7_engine/tests/ with fixes for the new package structure.
Includes golden tests that pin current outputs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from packages.p2oasys_scorer import (
    SCORER_VERSION,
    DEFAULT_MATRIX_PATH,
    load_p2oasys_matrix,
    compute_p2oasys_scores,
    compute_p2oasys_scores_with_trace,
    mean_of_top_two_highest,
    matrix_fingerprint,
    parse_measured_value,
)
from packages.p2oasys_scorer.utils import p2oasys_scorer


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "packages" / "p2oasys_scorer" / "fixtures"
GOLDEN_FIXTURE = FIXTURES_DIR / "scorer_golden_offline.json"


@pytest.fixture(scope="module")
def matrix():
    """Load the bundled P2OASys matrix."""
    return load_p2oasys_matrix(DEFAULT_MATRIX_PATH)


@pytest.fixture(scope="module")
def golden_data():
    """Load the golden test fixture."""
    with GOLDEN_FIXTURE.open() as f:
        return json.load(f)


# --------------------------------------------------------------------------- #
# Number parsing
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "raw, expected",
    [
        ("3,900", 3900.0),      # thousands separator, NOT 3.9
        ("3,9", 3.9),           # decimal comma
        ("1,234,567.8", 1234567.8),
        ("5000", 5000.0),
        ("0.05", 0.05),
        (2000, 2000.0),
        ("", None),
        ("nan", None),
    ],
)
def test_num_parses_commas_correctly(raw, expected):
    assert p2oasys_scorer._num(raw) == expected


def test_numeric_threshold_thousands_separator():
    assert p2oasys_scorer._parse_numeric_threshold(">1,000") == 1000.0


# --------------------------------------------------------------------------- #
# Site-style aggregation (top-two mean)
# --------------------------------------------------------------------------- #

def test_mean_of_top_two_empty():
    assert mean_of_top_two_highest([]) is None


def test_mean_of_top_two_single():
    assert mean_of_top_two_highest([8.0]) == 8.0


def test_mean_of_top_two_pair():
    assert mean_of_top_two_highest([10.0, 6.0]) == 8.0


def test_mean_of_top_two_takes_worst_two():
    assert mean_of_top_two_highest([2.0, 10.0, 4.0, 8.0]) == 9.0


# --------------------------------------------------------------------------- #
# Oral / dermal LD50 route requirements
# --------------------------------------------------------------------------- #

def _hd(toxicities, ghs=None):
    return {
        "ghs": ghs or {"h_codes": []},
        "toxicities": toxicities,
        "hazard_metrics": {"flash_point": [], "nfpa": [], "other_designations": []},
    }


def test_oral_ld50_requires_oral_route():
    hd = _hd([
        {"value": "LD50 500 mg/kg", "species_route": ["oral", "rat"]},
    ])
    got = p2oasys_scorer._extract_ld50_oral(hd)
    assert got is not None
    assert got["value"] == 500.0
    assert got["route"] == "oral"


def test_oral_ld50_accepts_intraperitoneal_rejects_iv():
    rej: list = []
    hd = _hd([
        {"value": "LD50 5 mg/kg", "species_route": ["ip", "mouse"]},
        {"value": "LD50 8 mg/kg", "species_route": ["iv", "rat"]},
    ])
    got = p2oasys_scorer._extract_ld50_oral(hd, rej)
    assert got is not None
    assert got["value"] == 5.0
    assert got["route"] == "oral"
    assert any("not oral" in str(r.get("reason", "")).lower() for r in rej)


def test_oral_ld50_accepts_gavage_and_po():
    for route in (["gavage", "rat"], ["p.o.", "rat"], ["po", "mouse"]):
        hd = _hd([{"value": "LD50 250 mg/kg", "species_route": route}])
        got = p2oasys_scorer._extract_ld50_oral(hd)
        assert got is not None, route
        assert got["value"] == 250.0


def test_dermal_ld50_no_oral_fallback():
    hd = _hd([
        {"value": "LD50 500 mg/kg", "species_route": ["oral", "rat"]},
    ])
    assert p2oasys_scorer._extract_ld50_dermal(hd) is None


# --------------------------------------------------------------------------- #
# Inhalation LC50 units
# --------------------------------------------------------------------------- #

def test_inhalation_lc50_ppm_thousands_separator():
    hd = _hd([
        {"value": "LC50 3,900 ppm inhalation rat", "species_route": ["inhalation", "rat"]},
    ])
    got = p2oasys_scorer._extract_lc50_inhalation(hd)
    assert got is not None
    assert got["value"] == 3900.0


def test_inhalation_mgm3_not_scored_as_ppm():
    rej: list = []
    hd = _hd([
        {"value": "LC50 500 mg/m3 inhalation rat", "species_route": ["inhalation", "rat"]},
    ])
    assert p2oasys_scorer._extract_lc50_inhalation(hd, rej) is None
    assert any("mg/m" in r["reason"] or "molecular weight" in r["reason"] for r in rej)


def test_inhalation_mgm3_converts_with_mw():
    hd = _hd([
        {"value": "LC50 1000 mg/m3 inhalation rat", "species_route": ["inhalation", "rat"]},
    ])
    hd["molecular_weight"] = 58.08
    got = p2oasys_scorer._extract_lc50_inhalation(hd)
    assert got is not None
    assert abs(got["value"] - (1000 * 24.45 / 58.08)) < 0.1
    assert got["source_unit"] == "mg/m3"


def test_qualifier_less_than_preserved():
    parsed = parse_measured_value("<50", higher_is_safer=True)
    assert parsed == {"value": 50.0, "qualifier": "<", "raw": "<50"}


# --------------------------------------------------------------------------- #
# IARC extraction
# --------------------------------------------------------------------------- #

def test_iarc_not_listed_returns_none():
    text = (
        "Not listed by IARC. Certain nitrosamines are classified by IARC as either "
        "probably or possibly carcinogenic to humans (Groups 2A and 2B, respectively). (L135)"
    )
    hd = _hd([{"value": text}])
    assert p2oasys_scorer._extract_iarc(hd) is None


def test_iarc_real_classification_extracted():
    hd = _hd([{"value": "This substance is classified by IARC in Group 1 (carcinogenic to humans)."}])
    assert p2oasys_scorer._extract_iarc(hd) == "1"


# --------------------------------------------------------------------------- #
# Matrix loading and fingerprint
# --------------------------------------------------------------------------- #

def test_matrix_loads_successfully(matrix):
    assert matrix is not None
    assert "Acute Human Effects" in matrix
    assert "Chronic Human Effects" in matrix
    assert "Physical Properties" in matrix


def test_matrix_fingerprint():
    fp = matrix_fingerprint(DEFAULT_MATRIX_PATH)
    assert fp["exists"] is True
    assert fp["sha256"] and len(fp["sha256"]) == 64
    assert fp["size_bytes"] and fp["size_bytes"] > 0


def test_scorer_version():
    assert SCORER_VERSION == "p2oasys_scorer_v6.7_bug_fixes"


# --------------------------------------------------------------------------- #
# Golden tests - pin current outputs
# --------------------------------------------------------------------------- #

def test_golden_fixture_exists():
    assert GOLDEN_FIXTURE.exists(), f"Golden fixture not found: {GOLDEN_FIXTURE}"


def test_golden_fixture_scorer_version(golden_data):
    assert golden_data["scorer_version"] == SCORER_VERSION


def test_golden_fixture_matrix_fingerprint(golden_data):
    expected_fp = golden_data["matrix_fingerprint"]
    actual_fp = matrix_fingerprint(DEFAULT_MATRIX_PATH)
    assert actual_fp["sha256"] == expected_fp["sha256"], "Matrix SHA256 mismatch"


def test_golden_benzene_like_scores(matrix, golden_data):
    """Test benzene-like case produces expected scores."""
    case = golden_data["cases"]["benzene_like"]
    hazard_data = case["hazard_data"]
    expected_scores = case["scores"]

    actual_scores = compute_p2oasys_scores(hazard_data, matrix)

    for category, expected_cat in expected_scores.items():
        if category.startswith("_"):
            continue
        assert category in actual_scores, f"Missing category: {category}"
        actual_cat = actual_scores[category]

        if "_category_max" in expected_cat:
            assert "_category_max" in actual_cat, f"Missing _category_max in {category}"
            assert abs(actual_cat["_category_max"] - expected_cat["_category_max"]) < 0.01, \
                f"Category max mismatch in {category}: {actual_cat['_category_max']} != {expected_cat['_category_max']}"


def test_golden_acetone_like_scores(matrix, golden_data):
    """Test acetone-like case produces expected scores."""
    case = golden_data["cases"]["acetone_like"]
    hazard_data = case["hazard_data"]
    expected_scores = case["scores"]

    actual_scores = compute_p2oasys_scores(hazard_data, matrix)

    for category, expected_cat in expected_scores.items():
        if category.startswith("_"):
            continue
        if category not in actual_scores:
            continue
        actual_cat = actual_scores[category]

        if "_category_max" in expected_cat and "_category_max" in actual_cat:
            assert abs(actual_cat["_category_max"] - expected_cat["_category_max"]) < 0.01, \
                f"Category max mismatch in {category}"


def test_golden_rollup_consistency(matrix, golden_data):
    """Verify that subcategory _max and category _category_max are consistent with mean-of-top-2."""
    for case_name, case in golden_data["cases"].items():
        hazard_data = case["hazard_data"]
        scores = compute_p2oasys_scores(hazard_data, matrix)

        for category, cat_data in scores.items():
            if not isinstance(cat_data, dict):
                continue

            subcat_maxima = []
            for subcat, subcat_data in cat_data.items():
                if subcat.startswith("_") or not isinstance(subcat_data, dict):
                    continue

                unit_scores = [
                    v for k, v in subcat_data.items()
                    if not k.startswith("_") and isinstance(v, (int, float))
                ]
                if unit_scores:
                    expected_subcat_max = mean_of_top_two_highest(unit_scores)
                    actual_subcat_max = subcat_data.get("_max")
                    if expected_subcat_max is not None and actual_subcat_max is not None:
                        assert abs(actual_subcat_max - expected_subcat_max) < 0.01, \
                            f"Subcat _max mismatch in {case_name}/{category}/{subcat}"
                    subcat_maxima.append(actual_subcat_max)

            if subcat_maxima:
                subcat_maxima_clean = [m for m in subcat_maxima if m is not None]
                expected_cat_max = mean_of_top_two_highest(subcat_maxima_clean)
                actual_cat_max = cat_data.get("_category_max")
                if expected_cat_max is not None and actual_cat_max is not None:
                    assert abs(actual_cat_max - expected_cat_max) < 0.01, \
                        f"Category _category_max mismatch in {case_name}/{category}"


def test_golden_trace_evidence(matrix, golden_data):
    """Verify trace evidence is populated correctly."""
    case = golden_data["cases"]["benzene_like"]
    hazard_data = case["hazard_data"]
    expected_trace = case["trace"]

    _, actual_trace = compute_p2oasys_scores_with_trace(hazard_data, matrix)

    assert actual_trace["scorer_version"] == expected_trace["scorer_version"]
    assert "evidence" in actual_trace
    assert "rejected" in actual_trace
    assert "scored" in actual_trace
    assert "missing" in actual_trace
    assert "category_status" in actual_trace

    expected_oral = expected_trace["evidence"]["oral_ld50"]
    actual_oral = actual_trace["evidence"]["oral_ld50"]
    if expected_oral and actual_oral:
        assert actual_oral["value"] == expected_oral["value"]


def test_golden_empty_case(matrix, golden_data):
    """Test empty hazard_data produces no scores."""
    case = golden_data["cases"]["empty"]
    hazard_data = case["hazard_data"]

    scores = compute_p2oasys_scores(hazard_data, matrix)

    for category, cat_data in scores.items():
        if isinstance(cat_data, dict):
            assert cat_data.get("_category_max") is None or cat_data == {}


# --------------------------------------------------------------------------- #
# End-to-end scoring
# --------------------------------------------------------------------------- #

def test_end_to_end_scoring_with_trace(matrix):
    """Test that scoring produces both scores and a decision trace."""
    hd = _hd(
        [{"value": "LD50 120 mg/kg", "species_route": ["oral", "rat"]}],
        ghs={"h_codes": ["H301"]},
    )
    scores_only = compute_p2oasys_scores(hd, matrix)
    scores, trace = compute_p2oasys_scores_with_trace(hd, matrix)

    assert scores_only == scores
    assert trace["scorer_version"] == SCORER_VERSION
    assert "evidence" in trace
    assert "rejected" in trace
    assert "scored" in trace
    assert "missing" in trace
    assert trace["evidence"]["oral_ld50"]["value"] == 120.0


# --------------------------------------------------------------------------- #
# Bug fixes - PR B
# --------------------------------------------------------------------------- #

def test_flash_point_high_value_is_safe(matrix):
    """High flash point (345°C like propanediol 504-63-2) should score 2 (safest).

    Bug: Previously, flash points above all thresholds scored 10 (most hazardous)
    instead of 2 (safest). High flash point means harder to ignite → safer.
    """
    hd = _hd([], ghs={"h_codes": []})
    hd["hazard_metrics"]["flash_point"] = ["345°C"]

    scores = compute_p2oasys_scores(hd, matrix)
    physical = scores.get("Physical Properties", {})
    flammability = physical.get("Flammability: Liquid", {})

    assert "Flash Point deg C" in flammability
    assert flammability["Flash Point deg C"] == 2, \
        f"High flash point 345°C should score 2 (safest), got {flammability['Flash Point deg C']}"


def test_flash_point_low_value_is_hazardous(matrix):
    """Low flash point (5°C) should score 10 (most hazardous)."""
    hd = _hd([], ghs={"h_codes": []})
    hd["hazard_metrics"]["flash_point"] = ["5°C"]

    scores = compute_p2oasys_scores(hd, matrix)
    physical = scores.get("Physical Properties", {})
    flammability = physical.get("Flammability: Liquid", {})

    assert flammability["Flash Point deg C"] == 10


@pytest.mark.parametrize(
    "flash_c, expected_score",
    [
        (5, 10),    # Below all thresholds
        (10, 10),   # At threshold
        (25, 8),
        (45, 6),
        (60, 4),
        (93, 2),
        (100, 2),   # Above highest threshold → safest
        (345, 2),   # Propanediol case
    ],
)
def test_flash_point_threshold_boundaries(matrix, flash_c, expected_score):
    """Flash point scores correctly at and between thresholds."""
    hd = _hd([], ghs={"h_codes": []})
    hd["hazard_metrics"]["flash_point"] = [f"{flash_c}°C"]

    scores = compute_p2oasys_scores(hd, matrix)
    actual = scores.get("Physical Properties", {}).get("Flammability: Liquid", {}).get("Flash Point deg C")

    assert actual == expected_score, f"Flash {flash_c}°C: expected {expected_score}, got {actual}"


def test_ecosar_lc50_above_solubility_excluded_from_score(matrix):
    """Predicted LC50 ABOVE water solubility must NOT drive a high Eco score.

    ECOSAR/GHS rule: If LC50 > water_solubility, the chemical cannot dissolve
    enough to reach the toxic concentration. "No effect at saturation" means
    this value should NOT drive Eco scoring.
    """
    hd = _hd([], ghs={"h_codes": []})
    hd["lc50_aquatic_mg_l"] = {"value": 0.01, "predicted": True}  # Very low LC50
    hd["water_solubility_mg_l"] = {"value": 1e-6, "predicted": True}  # LOWER solubility limit

    scores, trace = compute_p2oasys_scores_with_trace(hd, matrix)

    aquatic_ev = trace["evidence"].get("aquatic_lc50")
    assert aquatic_ev is not None
    assert aquatic_ev.get("beyond_solubility") is True, "Should flag beyond_solubility"
    # Value should be kept for trace but NOT scored
    assert aquatic_ev["value"] == 0.01, f"Should keep original value for trace"

    # Eco score should NOT be 10 from this implausible LC50
    eco = scores.get("Ecological Hazards", {})
    aquatic_sub = eco.get("Acute Aquatic Toxicity", {})
    # The LC50 unit should NOT be scored (excluded)
    assert "Acute Fish LC50 (mg/l)" not in aquatic_sub or aquatic_sub.get("Acute Fish LC50 (mg/l)") is None, \
        "Beyond-solubility LC50 should NOT produce a score"

    # Check that the missing list records the exclusion
    missing = [m for m in trace["missing"] if "Aquatic" in m.get("subcategory", "")]
    excluded = [m for m in missing if "excluded" in m.get("reason", "").lower()]
    assert len(excluded) > 0, "Should record exclusion in missing list"


def test_ecosar_lc50_below_solubility_is_scored(matrix):
    """Predicted LC50 BELOW water solubility is valid and should be scored.

    When LC50 < water_solubility, the chemical CAN dissolve to that toxic
    concentration. This is a valid prediction that should be scored normally.
    """
    hd = _hd([], ghs={"h_codes": []})
    hd["lc50_aquatic_mg_l"] = {"value": 0.01, "predicted": True}  # BELOW solubility
    hd["water_solubility_mg_l"] = {"value": 0.1, "predicted": True}  # HIGHER solubility

    scores, trace = compute_p2oasys_scores_with_trace(hd, matrix)

    aquatic_ev = trace["evidence"].get("aquatic_lc50")
    assert aquatic_ev is not None
    assert aquatic_ev.get("beyond_solubility") is False, "Should NOT flag"
    assert aquatic_ev["value"] == 0.01

    # Eco score SHOULD be driven by this valid LC50
    eco = scores.get("Ecological Hazards", {})
    aquatic_sub = eco.get("Acute Aquatic Toxicity", {})
    assert aquatic_sub.get("_max") is not None, "Valid LC50 should produce a score"


def test_ecosar_very_low_lc50_with_high_logkow_excluded():
    """Extremely low predicted LC50 with high logKow must NOT drive Eco 10.

    Cases like CAS 7235-40-7 (LC50 4.1e-12 mg/L, logKow 6.75) are beyond
    achievable water concentration. These must NOT produce Eco 10.
    """
    hd = _hd([], ghs={"h_codes": []})
    hd["lc50_aquatic_mg_l"] = {"value": 4.1e-12, "predicted": True}
    hd["log_kow"] = {"value": 6.75, "predicted": True}  # High logKow like beta-carotene

    scores, trace = compute_p2oasys_scores_with_trace(hd, load_p2oasys_matrix(DEFAULT_MATRIX_PATH))

    aquatic_ev = trace["evidence"].get("aquatic_lc50")
    assert aquatic_ev is not None
    assert aquatic_ev.get("low_confidence") is True, "Should flag low_confidence"

    # Eco score should NOT be 10 from this implausible LC50
    eco = scores.get("Ecological Hazards", {})
    cat_max = eco.get("_category_max")
    # Either no score or not 10
    assert cat_max is None or cat_max < 10, \
        f"Low-confidence LC50 should NOT drive Eco 10, got {cat_max}"


def test_measured_lc50_is_scored_even_with_high_logkow():
    """Measured (non-predicted) LC50 values should be scored even with high logKow.

    Only predicted values from ECOSAR/QSAR should be excluded for logKow heuristic.
    """
    hd = _hd([], ghs={"h_codes": []})
    hd["lc50_aquatic_mg_l"] = {"value": 0.001, "predicted": False}  # Measured
    hd["log_kow"] = {"value": 6.0, "predicted": True}  # High logKow

    scores, trace = compute_p2oasys_scores_with_trace(hd, load_p2oasys_matrix(DEFAULT_MATRIX_PATH))

    aquatic_ev = trace["evidence"].get("aquatic_lc50")
    assert aquatic_ev is not None
    assert not aquatic_ev.get("low_confidence", False), "Measured values not flagged"

    # Measured value SHOULD be scored
    eco = scores.get("Ecological Hazards", {})
    aquatic_sub = eco.get("Acute Aquatic Toxicity", {})
    assert aquatic_sub.get("_max") is not None, "Measured LC50 should be scored"


def test_predicted_flag_propagates_to_subcategory(matrix):
    """Predicted flag propagates from unit to subcategory level."""
    hd = _hd([], ghs={"h_codes": []})
    hd["hazard_metrics"]["flash_point"] = ["25°C"]  # Measured data

    scores, trace = compute_p2oasys_scores_with_trace(hd, matrix)

    physical = scores.get("Physical Properties", {})
    flammability = physical.get("Flammability: Liquid", {})
    assert "_predicted" in flammability
    assert flammability["_predicted"] is False, "Non-predicted data should have _predicted=False"


def test_predicted_flag_propagates_to_category(matrix):
    """Predicted flag propagates from subcategory to category level."""
    hd = _hd(
        [{"value": "LD50 100 mg/kg", "species_route": ["oral", "rat"], "predicted": True}],
        ghs={"h_codes": []},
    )

    scores, trace = compute_p2oasys_scores_with_trace(hd, matrix)

    acute = scores.get("Acute Human Effects", {})
    assert "_category_predicted" in acute
    assert acute["_category_predicted"] is True, "All-predicted category should have _category_predicted=True"


def test_overall_score_computed(matrix):
    """Overall score is computed as MAX of Auto6 categories."""
    hd = _hd(
        [{"value": "LD50 100 mg/kg", "species_route": ["oral", "rat"]}],
        ghs={"h_codes": ["H301"]},  # Acute tox category 3
    )
    hd["hazard_metrics"]["flash_point"] = ["25°C"]  # Physical score

    scores, trace = compute_p2oasys_scores_with_trace(hd, matrix)

    assert "_overall" in scores
    overall = scores["_overall"]
    assert overall["score"] is not None
    assert overall["auto6_count"] > 0
    assert "categories_at_8_or_above" in overall
    assert "measured_categories_at_8_or_above" in overall


def test_overall_excludes_process_lifecycle(matrix):
    """Process and Life Cycle categories are excluded from Auto6 overall."""
    from packages.p2oasys_scorer.utils.p2oasys_scorer import AUTO6_CATEGORIES

    assert "Process Factors" not in AUTO6_CATEGORIES
    assert "Life Cycle Factors" not in AUTO6_CATEGORIES
    assert "Acute Human Effects" in AUTO6_CATEGORIES
    assert len(AUTO6_CATEGORIES) == 6


def test_scores_rounded_to_2_significant_digits(matrix):
    """Scores are rounded to 2 significant digits."""
    hd = _hd(
        [
            {"value": "LD50 120 mg/kg", "species_route": ["oral", "rat"]},
            {"value": "LD50 180 mg/kg", "species_route": ["oral", "rat"]},
        ],
        ghs={"h_codes": []},
    )

    scores, _ = compute_p2oasys_scores_with_trace(hd, matrix)

    acute = scores.get("Acute Human Effects", {})
    oral_tox = acute.get("Oral Toxicity", {})
    if "_max" in oral_tox:
        max_val = oral_tox["_max"]
        assert isinstance(max_val, float)
        str_val = f"{max_val:.10g}"
        non_zero_digits = len([c for c in str_val.replace(".", "") if c != "0" and c.isdigit()])
        assert non_zero_digits <= 2, f"Score {max_val} has more than 2 significant digits"
