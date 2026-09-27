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
    assert SCORER_VERSION == "p2oasys_scorer_v6.6_site_top2"


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
