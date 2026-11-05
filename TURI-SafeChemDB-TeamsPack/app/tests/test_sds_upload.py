"""Uploaded SDS: one clear product CAS fills the row; mixtures are not copied."""

from packages.doss_core.schema import empty_row
from packages.doss_core.sds_upload import (
    SHARE_SDS_MESSAGE,
    apply_uploaded_sds,
    cas_checksum_ok,
    review_sds_text,
)

_PURE = """
SECTION 1: IDENTIFICATION
Product name: Acetone
CAS No: 67-64-1

SECTION 3: COMPOSITION/INFORMATION ON INGREDIENTS
Acetone 67-64-1 100%

SECTION 9: PHYSICAL AND CHEMICAL PROPERTIES
Flash point: -20 C
Boiling point: 56 C

SECTION 15: REGULATORY
Related listing 108-88-3
"""

_MIXTURE = """
SECTION 1: IDENTIFICATION
Product name: Cleaning blend

SECTION 3: COMPOSITION/INFORMATION ON INGREDIENTS
Ethanol 64-17-5 70%
Water 7732-18-5 30%
"""

_TWO_NAMES = """
SECTION 1: IDENTIFICATION
Component A CAS 67-64-1
Component B CAS 64-17-5
The rest of this identification block is long enough to pass the text-length check.
"""


def test_checksum_accepts_acetone_and_rejects_a_bad_digit():
    assert cas_checksum_ok("67", "64", "1")
    assert not cas_checksum_ok("67", "64", "2")


def test_pure_substance_fills_an_empty_flash_point_and_mentions_other_cas():
    review = review_sds_text(_PURE, requested_cas="67-64-1", filename="acetone.pdf")
    assert review["status"] == "ok"
    assert review["product_cas"] == "67-64-1"
    assert "108-88-3" in review["all_cas"]
    assert review["share_sds"] is True
    assert SHARE_SDS_MESSAGE in review["message"]
    assert review["fields"]["flash_point_c"] == -20.0

    row = empty_row()
    row["Flash Point (C)"] = "-"
    apply_uploaded_sds(row, review)
    assert row["Flash Point (C)"] == "-20.0"
    assert row["_prop_sources"]["Flash Point (C)"] == "uploaded SDS"


def test_en_dash_cas_still_matches():
    text = _PURE.replace("67-64-1", "67\u201364\u20131")
    review = review_sds_text(text, requested_cas="67-64-1", filename="acetone.pdf")
    assert review["status"] == "ok"
    assert review["product_cas"] == "67-64-1"


def test_mixture_is_not_copied_and_asks_for_the_file():
    review = review_sds_text(_MIXTURE, requested_cas="64-17-5", filename="blend.pdf")
    assert review["status"] == "mixture"
    assert review["fields"] == {}
    assert review["share_sds"] is True
    assert SHARE_SDS_MESSAGE in review["message"]
    row = empty_row()
    apply_uploaded_sds(row, review)
    assert row["Flash Point (C)"] == "-"
    assert row["_sds_upload"]["status"] == "mixture"


def test_wrong_cas_is_not_applied():
    review = review_sds_text(_PURE, requested_cas="64-17-5", filename="acetone.pdf")
    assert review["status"] == "mismatch"
    assert SHARE_SDS_MESSAGE in review["message"]
    row = empty_row()
    apply_uploaded_sds(row, review)
    assert row["Flash Point (C)"] == "-"


def test_two_identity_cas_numbers_are_not_applied():
    review = review_sds_text(_TWO_NAMES, requested_cas="67-64-1", filename="two.pdf")
    assert review["status"] == "several_cas"
    assert review["share_sds"] is True


def test_uploaded_sds_replaces_an_existing_flash_point():
    review = review_sds_text(_PURE, requested_cas="67-64-1", filename="acetone.pdf")
    row = empty_row()
    row["Flash Point (C)"] = "12.0"
    row["_prop_sources"] = {"Flash Point (C)": "PubChem"}
    apply_uploaded_sds(row, review)
    assert row["Flash Point (C)"] == "-20.0"
    assert row["_prop_sources"]["Flash Point (C)"] == "uploaded SDS"
    assert row["SDS Link"] == "Uploaded file: acetone.pdf"


def test_sds_without_a_typed_cas_still_identifies_the_product():
    review = review_sds_text(_PURE, filename="acetone.pdf")
    assert review["status"] == "ok"
    assert review["product_cas"] == "67-64-1"


def test_split_section_header_still_finds_one_product():
    text = """
SECTION 1
Identification of the substance
Product identifier
CAS No.
67-64-1

SECTION 3
Composition
Acetone 67-64-1 99 %

SECTION 9
Physical and chemical properties
Flash point: -17 C

SECTION 15
Regulatory information
Also listed 108-88-3
"""
    review = review_sds_text(text, filename="split.pdf")
    assert review["status"] == "ok"
    assert review["product_cas"] == "67-64-1"
    assert review["fields"]["flash_point_c"] == -17.0


def test_unreadable_text_asks_for_the_file():
    review = review_sds_text("   ", filename="scan.pdf")
    assert review["status"] == "unreadable"
    assert SHARE_SDS_MESSAGE in review["message"]
