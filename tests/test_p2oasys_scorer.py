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


@pytest.mark.parametrize(
    "cell_value,expected",
    [
        ("30-200", 200.0),       # Range: use upper bound
        (">300-1000", 1000.0),   # Range with prefix: use upper bound
        ("0.1-1.0", 1.0),        # Decimal range: use upper bound
        ("<30", 30.0),           # Non-range: use the number
        (">1000", 1000.0),       # Non-range: use the number
    ],
)
def test_numeric_threshold_range_uses_upper_bound(cell_value, expected):
    """Range cells like '30-200' return upper bound (200), not lower (30)."""
    assert p2oasys_scorer._parse_numeric_threshold(cell_value) == expected


# --------------------------------------------------------------------------- #
# Expert-style aggregation (MAX - worst hazard wins)
# Per expert1228: subcategory = max unit score, category = max subcategory score
# --------------------------------------------------------------------------- #

def test_max_score_empty():
    assert mean_of_top_two_highest([]) is None


def test_max_score_single():
    assert mean_of_top_two_highest([8.0]) == 8.0


def test_max_score_returns_highest():
    """MAX aggregation: highest score wins (not average of top 2)."""
    assert mean_of_top_two_highest([10.0, 6.0]) == 10.0


def test_max_score_from_many():
    """MAX of [2, 10, 4, 8] = 10 (not 9.0 from mean of top 2)."""
    assert mean_of_top_two_highest([2.0, 10.0, 4.0, 8.0]) == 10.0


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


def test_oral_ld50_rejects_intraperitoneal_and_iv():
    """Intraperitoneal (i.p.) and IV routes are NOT oral - both rejected."""
    rej: list = []
    hd = _hd([
        {"value": "LD50 5 mg/kg", "species_route": ["ip", "mouse"]},
        {"value": "LD50 8 mg/kg", "species_route": ["iv", "rat"]},
    ])
    got = p2oasys_scorer._extract_ld50_oral(hd, rej)
    assert got is None, "Neither i.p. nor i.v. should be accepted as oral"
    assert len(rej) == 2, "Both routes should be rejected"
    assert all("not oral" in str(r.get("reason", "")).lower() for r in rej)


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
    assert SCORER_VERSION == "p2oasys_scorer_v7.0_expert_alignment"


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


@pytest.mark.parametrize(
    "reactivity_rating,expected_score",
    [
        (0, 2),
        (1, 4),
        (2, 6),
        (3, 8),
        (4, 10),
    ],
)
def test_nfpa_reactivity_scored(matrix, reactivity_rating, expected_score):
    """NFPA Reactivity rating is extracted and scored correctly."""
    hd = _hd([], ghs={"h_codes": []})
    hd["hazard_metrics"]["nfpa"] = [f"Reactivity {reactivity_rating}"]

    scores, trace = compute_p2oasys_scores_with_trace(hd, matrix)

    evidence = trace.get("evidence", {})
    assert evidence.get("nfpa_reactivity") == reactivity_rating

    physical = scores.get("Physical Properties", {})
    reactivity_sub = physical.get("Reactivity", {})
    nfpa_score = reactivity_sub.get("NFPA/HMIS 0,1,2,3,4")
    assert nfpa_score == expected_score, f"NFPA Reactivity {reactivity_rating} → score {expected_score}"


@pytest.mark.parametrize(
    "chv_value,expected_score",
    [
        (20.0, 2),    # ChV >= 10 → score 2
        (5.0, 4),     # ChV >= 5 → score 4
        (1.0, 6),     # ChV >= 1 → score 6
        (0.5, 8),     # ChV >= 0.1 → score 8
        (0.05, 10),   # ChV < 0.1 → score 10
    ],
)
def test_chv_aquatic_scored(matrix, chv_value, expected_score):
    """ECOSAR Chronic Value (ChV) is extracted and scored correctly."""
    hd = _hd([], ghs={"h_codes": []})
    hd["chv_aquatic_mg_l"] = {"value": chv_value, "predicted": False}

    scores, trace = compute_p2oasys_scores_with_trace(hd, matrix)

    evidence = trace.get("evidence", {})
    assert evidence.get("aquatic_chv") is not None
    assert evidence["aquatic_chv"]["value"] == chv_value

    eco = scores.get("Ecological Hazards", {})
    chronic_sub = eco.get("Chronic Aquatic Toxicity (fish, crustacea or algae)", {})
    chv_score = chronic_sub.get("ChV mg/l")
    assert chv_score == expected_score, f"ChV {chv_value} mg/L → score {expected_score}"


def test_measured_lc50_takes_precedence_over_predicted(matrix):
    """Measured aquatic LC50 values take precedence over lower predicted (ECOSAR) values."""
    hd = _hd([], ghs={"h_codes": []})
    # Predicted value is lower (more hazardous) but measured should win
    hd["lc50_aquatic_mg_l"] = {"value": 1.0, "predicted": True}  # ECOSAR prediction
    hd["toxicities"] = [
        {"value": "LC50 10.0 mg/L fish", "predicted": False}  # Measured
    ]

    scores, trace = compute_p2oasys_scores_with_trace(hd, matrix)

    evidence = trace.get("evidence", {})
    lc50_ev = evidence.get("aquatic_lc50")
    assert lc50_ev is not None
    assert lc50_ev["value"] == 10.0, "Measured value (10.0) should be used, not predicted (1.0)"
    assert lc50_ev["predicted"] is False, "Evidence should be marked as measured (not predicted)"

    # The less hazardous measured value means a lower Eco score
    eco = scores.get("Ecological Hazards", {})
    aquatic_sub = eco.get("Acute Aquatic Toxicity", {})
    lc50_score = aquatic_sub.get("Acute Fish LC50 (mg/l)")
    # LC50 10.0 mg/L should score lower than LC50 1.0 mg/L
    assert lc50_score is not None
    assert lc50_score < 10, "Measured 10.0 mg/L should not score the highest hazard level"


# --------------------------------------------------------------------------- #
# Gabriel's Round 3.2 requested tests
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "gwp_value,expected_score",
    [
        (50, 4),    # GWP 50 → band 30-200 → score 4
        (250, 6),   # GWP 250 → band 200-300 → score 6
        (500, 8),   # GWP 500 → band 300-1000 → score 8
    ],
)
def test_gwp_range_scoring(matrix, gwp_value, expected_score):
    """GWP range parsing: upper bound is used for threshold comparison."""
    hd = _hd([], ghs={"h_codes": []})
    hd["hazard_metrics"]["gwp100"] = [gwp_value]

    scores, _ = compute_p2oasys_scores_with_trace(hd, matrix)

    atmo = scores.get("Atmospheric Hazard", {})
    atmo_sub = atmo.get("Atmospheric Hazard", {})
    gwp_score = atmo_sub.get("GWP Relative to CO2")
    assert gwp_score == expected_score, f"GWP {gwp_value} should score {expected_score}, got {gwp_score}"


@pytest.mark.parametrize(
    "cas,name,lc50,logkow",
    [
        ("27841-04-9", "Neopentyl glycol diheptanoate", 0.013, 6.76),
        ("31566-31-1", "Glyceryl stearate", 0.017, 5.18),
        ("7235-40-7", "Beta-carotene", 4.1e-12, 6.75),
    ],
)
def test_olaplex_lipophilic_exclusion(matrix, cas, name, lc50, logkow):
    """Olaplex cases: predicted LC50 with high logKow and no solubility → excluded."""
    hd = _hd([], ghs={"h_codes": []})
    hd["lc50_aquatic_mg_l"] = {"value": lc50, "predicted": True}
    hd["log_kow"] = {"value": logkow, "predicted": True}
    # No solubility data provided

    scores, trace = compute_p2oasys_scores_with_trace(hd, matrix)

    evidence = trace.get("evidence", {})
    lc50_ev = evidence.get("aquatic_lc50", {})
    assert lc50_ev.get("low_confidence") is True, f"{cas} ({name}): should be flagged low_confidence"

    eco = scores.get("Ecological Hazards", {})
    aquatic = eco.get("Acute Aquatic Toxicity", {})
    assert aquatic.get("_max") is None, f"{cas} ({name}): should NOT score Eco 10"


def test_intraperitoneal_ld50_not_oral(matrix):
    """Intraperitoneal (i.p.) LD50 should NOT be scored as oral LD50."""
    hd = _hd([], ghs={"h_codes": []})
    hd["toxicities"] = [
        {"value": "Intraperitoneal LD50 (mouse) = 200 mg/kg; [RTECS]", "species_route": ["mouse", "ip"]}
    ]

    scores, trace = compute_p2oasys_scores_with_trace(hd, matrix)

    evidence = trace.get("evidence", {})
    assert evidence.get("oral_ld50") is None, "i.p. LD50 should not be used as oral LD50"

    # Check rejections
    rejected = trace.get("rejected", [])
    ip_rejections = [r for r in rejected if "not oral" in str(r.get("reason", "")).lower()]
    assert len(ip_rejections) > 0, "i.p. route should be rejected with 'not oral' reason"


def test_process_factors_not_auto_scored(matrix):
    """Process Factors should NOT receive auto-scored values from physical properties."""
    hd = _hd([], ghs={"h_codes": []})
    hd["hazard_metrics"]["flash_point"] = ["25°C"]  # Flash point data

    scores, _ = compute_p2oasys_scores_with_trace(hd, matrix)

    process = scores.get("Process Factors", {})
    heat = process.get("Heat", {})

    # WBGT should NOT be scored with flash point
    assert "WBGT, deg C" not in heat or heat.get("WBGT, deg C") is None, \
        "Flash point should not auto-score WBGT in Process Factors"

    # But Physical Properties > Flammability SHOULD have flash point
    physical = scores.get("Physical Properties", {})
    flammability = physical.get("Flammability: Liquid", {})
    assert "Flash Point deg C" in flammability, "Flash point should score in Physical Properties"


def test_predicted_only_status_label(matrix):
    """Predicted-only evidence should have STATUS_PREDICTED_ONLY in trace."""
    from packages.p2oasys_scorer.utils.p2oasys_scorer import STATUS_PREDICTED_ONLY

    hd = _hd([], ghs={"h_codes": []})
    hd["lc50_aquatic_mg_l"] = {"value": 10.0, "predicted": True}

    scores, trace = compute_p2oasys_scores_with_trace(hd, matrix)

    scored = trace.get("scored", [])
    lc50_scored = [s for s in scored if "LC50" in s.get("unit", "") and "Aquatic" in s.get("subcategory", "")]

    assert len(lc50_scored) > 0, "LC50 should be scored"
    for entry in lc50_scored:
        assert entry.get("status") == STATUS_PREDICTED_ONLY, \
            f"Predicted-only evidence should have status '{STATUS_PREDICTED_ONLY}', got '{entry.get('status')}'"
        assert entry.get("predicted") is True


# --------------------------------------------------------------------------- #
# Band corrections (Fix 7, expert1228)
# --------------------------------------------------------------------------- #

def test_acid_rain_s_or_n_minimum_8(matrix):
    """Acid Rain Formation: S or N in SMILES → minimum score 8 (Fix 7)."""
    hd = _hd([], ghs={"h_codes": []})
    hd["smiles"] = "c1ccccc1S"  # Benzene with S
    hd["toxicities"] = [
        {"value": "Does not contain S or N"},  # Would normally score 2
    ]

    scores, trace = compute_p2oasys_scores_with_trace(hd, matrix)

    evidence = trace.get("evidence", {})
    assert evidence.get("has_s_or_n") is True, "Should detect S in SMILES"

    atmo = scores.get("Atmospheric Hazard", {})
    acid_rain = atmo.get("Acid Rain Formation", {})
    acid_rain_score = acid_rain.get("Key Phrases")

    assert acid_rain_score is not None, "Should have Acid Rain score"
    assert acid_rain_score >= 8, f"S in SMILES should give minimum 8, got {acid_rain_score}"


def test_acid_rain_nitrogen_minimum_8(matrix):
    """Acid Rain Formation: N in SMILES → minimum score 8 (Fix 7)."""
    hd = _hd([], ghs={"h_codes": []})
    hd["smiles"] = "c1ccc(N)cc1"  # Aniline
    hd["toxicities"] = [
        {"value": "Does not contain S or N"},  # Would normally score 2
    ]

    scores, trace = compute_p2oasys_scores_with_trace(hd, matrix)

    evidence = trace.get("evidence", {})
    assert evidence.get("has_s_or_n") is True, "Should detect N in SMILES"

    atmo = scores.get("Atmospheric Hazard", {})
    acid_rain = atmo.get("Acid Rain Formation", {})
    acid_rain_score = acid_rain.get("Key Phrases")

    assert acid_rain_score is not None, "Should have Acid Rain score"
    assert acid_rain_score >= 8, f"N in SMILES should give minimum 8, got {acid_rain_score}"


def test_acid_rain_no_s_or_n_no_correction(matrix):
    """Acid Rain Formation: no S or N in SMILES → no band correction."""
    hd = _hd([], ghs={"h_codes": []})
    hd["smiles"] = "c1ccccc1"  # Benzene without S or N
    hd["toxicities"] = [
        {"value": "Does not contain S or N"},  # Should score 2
    ]

    scores, trace = compute_p2oasys_scores_with_trace(hd, matrix)

    evidence = trace.get("evidence", {})
    assert evidence.get("has_s_or_n") is False, "Should NOT detect S or N in SMILES"

    atmo = scores.get("Atmospheric Hazard", {})
    acid_rain = atmo.get("Acid Rain Formation", {})
    acid_rain_score = acid_rain.get("Key Phrases")

    assert acid_rain_score == 2, f"No S or N should score 2, got {acid_rain_score}"


def test_neshap_hap_listed_scores_10(matrix):
    """NESHAP: listed HAP → score 10 (Fix 7)."""
    hd = _hd([], ghs={"h_codes": []})
    hd["toxicities"] = [
        {"value": "Listed as NESHAP Hazardous Air Pollutant"},
        {"value": "Not listed as EPA hazardous air pollutant"},  # Would score 2
    ]

    scores, trace = compute_p2oasys_scores_with_trace(hd, matrix)

    evidence = trace.get("evidence", {})
    assert evidence.get("is_neshap_hap") is True, "Should detect NESHAP HAP"

    atmo = scores.get("Atmospheric Hazard", {})
    neshap = atmo.get("NESHAP", {})
    neshap_score = neshap.get("Key Phrases")

    assert neshap_score == 10, f"NESHAP HAP should score 10, got {neshap_score}"


def test_neshap_not_listed_no_correction(matrix):
    """NESHAP: not listed HAP → no band correction."""
    hd = _hd([], ghs={"h_codes": []})
    hd["toxicities"] = [
        {"value": "Not listed as EPA hazardous air pollutant"},  # Score 2
    ]

    scores, trace = compute_p2oasys_scores_with_trace(hd, matrix)

    evidence = trace.get("evidence", {})
    assert evidence.get("is_neshap_hap") is False, "Should NOT detect NESHAP HAP"

    atmo = scores.get("Atmospheric Hazard", {})
    neshap = atmo.get("NESHAP", {})
    neshap_score = neshap.get("Key Phrases")

    assert neshap_score == 2, f"Not listed HAP should score 2, got {neshap_score}"


# --------------------------------------------------------------------------- #
# ECOSAR gap-fill rules (Gabriel's decision)
# --------------------------------------------------------------------------- #

def test_measured_wins_over_ecosar(matrix):
    """Measured aquatic data ALWAYS wins over ECOSAR predictions (Gabriel's rule)."""
    hd = _hd([], ghs={"h_codes": []})
    # Predicted (ECOSAR) value is lower (more hazardous)
    hd["lc50_aquatic_mg_l"] = {"value": 0.01, "predicted": True}  # Would score 10
    # Measured value is higher (less hazardous)
    hd["toxicities"] = [
        {"value": "LC50 100 mg/L fish", "predicted": False},  # Should score 4
    ]

    scores, trace = compute_p2oasys_scores_with_trace(hd, matrix)

    evidence = trace.get("evidence", {})
    lc50_ev = evidence.get("aquatic_lc50")

    assert lc50_ev is not None
    assert lc50_ev["value"] == 100.0, "Measured 100 mg/L should be used, not predicted 0.01"
    assert lc50_ev["predicted"] is False, "Should use measured data"

    eco = scores.get("Ecological Hazards", {})
    aquatic = eco.get("Acute Aquatic Toxicity", {})
    lc50_score = aquatic.get("Acute Fish LC50 (mg/l)")

    # LC50 100 mg/L scores lower than LC50 0.01 mg/L
    assert lc50_score is not None
    assert lc50_score < 10, "Measured 100 mg/L should NOT score 10 (ECOSAR 0.01 should be ignored)"


def test_ecosar_fills_gap(matrix):
    """ECOSAR fills Ecological subcategories when no measured data exists (Gabriel's rule)."""
    hd = _hd([], ghs={"h_codes": []})
    # Only predicted (ECOSAR) value, no measured
    hd["lc50_aquatic_mg_l"] = {"value": 5.0, "predicted": True}

    scores, trace = compute_p2oasys_scores_with_trace(hd, matrix)

    evidence = trace.get("evidence", {})
    lc50_ev = evidence.get("aquatic_lc50")

    assert lc50_ev is not None
    assert lc50_ev["value"] == 5.0, "ECOSAR value should be used when no measured"
    assert lc50_ev["predicted"] is True, "Should be marked as predicted"

    eco = scores.get("Ecological Hazards", {})
    aquatic = eco.get("Acute Aquatic Toxicity", {})
    lc50_score = aquatic.get("Acute Fish LC50 (mg/l)")

    assert lc50_score is not None, "ECOSAR should fill gap when no measured data"

    scored = trace.get("scored", [])
    lc50_scored = [s for s in scored if "LC50" in s.get("unit", "") and "Aquatic" in s.get("subcategory", "")]
    assert len(lc50_scored) > 0
    assert all(s.get("predicted") is True for s in lc50_scored), "ECOSAR-derived units must be labelled predicted=true"


def test_ghs_aquatic_h_codes_count_as_measured(matrix):
    """GHS aquatic H-codes (H400-H413) count as measured data for ECOSAR override."""
    hd = _hd([], ghs={"h_codes": ["H411"]})  # GHS chronic aquatic hazard
    # Predicted (ECOSAR) value
    hd["lc50_aquatic_mg_l"] = {"value": 0.001, "predicted": True}  # Would score 10

    scores, trace = compute_p2oasys_scores_with_trace(hd, matrix)

    eco = scores.get("Ecological Hazards", {})
    aquatic = eco.get("Acute Aquatic Toxicity", {})

    # H411 triggers GHS scoring which should be used
    assert aquatic.get("_max") is not None
    # GHS H codes provide category-level scores that may differ from raw LC50
