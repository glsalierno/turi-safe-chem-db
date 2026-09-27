"""Bundled harvest/auto P2OASys sqlite is visible to DoSS without a sibling GHaz7 tree."""
from __future__ import annotations

from packages.p2oasys_core.lookup import (
    cas_catalog_count,
    default_lookup_db_path,
    load_cas_catalog,
    load_expert_csv,
    lookup_expert_csv,
    resolve_p2oasys,
)

# Harvest CAS not in the 62-set expert CSV overlay.
HARVEST_ONLY_CAS = "100-37-8"


def test_bundled_lookup_db_exists():
    path = default_lookup_db_path()
    assert path.is_file(), path
    assert path.name == "p2oasys_score_lookup.sqlite"


def test_harvest_cas_uses_sqlite_expert_not_priority62_csv():
    expert_df = load_expert_csv()
    assert lookup_expert_csv(HARVEST_ONLY_CAS, expert_df) is None
    hit = resolve_p2oasys(HARVEST_ONLY_CAS, expert_df)
    assert hit["source"] == "expert"
    assert hit["overall"] != "-"
    assert "sqlite" in str(hit.get("detail") or "")


def test_priority62_csv_still_wins_for_acetone():
    expert_df = load_expert_csv()
    hit = resolve_p2oasys("67-64-1", expert_df)
    assert hit["source"] == "expert"
    assert hit["detail"] == "expert_csv"


def test_load_cas_catalog_returns_universe():
    """Catalog loader returns the full P2OASys universe from SQLite."""
    catalog = load_cas_catalog()
    assert len(catalog) > 100, "Expected large universe catalog"
    assert len(catalog) > 62, "Universe should be larger than priority-62 set"
    first = catalog[0]
    assert "cas" in first
    assert "name" in first
    assert "has_expert" in first
    assert "has_auto" in first


def test_cas_catalog_count_matches_load():
    """cas_catalog_count returns same count as load_cas_catalog."""
    count = cas_catalog_count()
    catalog = load_cas_catalog()
    assert count == len(catalog)
    assert count > 0


def test_catalog_includes_harvest_only_cas():
    """Universe catalog includes CAS that is NOT in priority-62 CSV."""
    catalog = load_cas_catalog()
    cas_set = {item["cas"].replace("-", "") for item in catalog}
    harvest_digits = HARVEST_ONLY_CAS.replace("-", "")
    assert harvest_digits in cas_set or HARVEST_ONLY_CAS in {item["cas"] for item in catalog}


def test_resolve_p2oasys_without_csv_uses_sqlite():
    """Without expert CSV, resolve_p2oasys falls through to SQLite expert/auto."""
    hit = resolve_p2oasys("67-64-1", expert_df=None)
    assert hit["source"] in ("expert", "auto")
    assert hit["overall"] != "-"
    assert "sqlite" in str(hit.get("detail") or "")


def test_resolve_acetone_without_csv_finds_score():
    """Acetone should resolve from SQLite when no CSV is provided."""
    hit = resolve_p2oasys("67-64-1", expert_df=None)
    assert hit["source"] in ("expert", "auto")
    assert hit["overall"] != "-"


# --------------------------------------------------------------------------- #
# Bug fixes - PR B
# --------------------------------------------------------------------------- #

def test_xylenes_name_not_methanol():
    """CAS 1330-20-7 (Xylenes) should NOT have name_auto='methanol'.

    Data bug: The original harvest incorrectly assigned methanol's name/data
    to the xylenes row. This test verifies the fix.
    """
    import sqlite3
    from packages.p2oasys_core.lookup import default_lookup_db_path

    conn = sqlite3.connect(str(default_lookup_db_path()))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT name_expert, name_auto FROM by_cas WHERE cas = '1330-20-7'"
        ).fetchone()
        assert row is not None, "Xylenes (1330-20-7) not found in database"
        assert row["name_expert"] == "Xylenes"
        name_auto = row["name_auto"].lower() if row["name_auto"] else ""
        assert "methanol" not in name_auto, \
            f"Xylenes name_auto incorrectly contains 'methanol': {row['name_auto']}"
        assert "xylene" in name_auto, \
            f"Xylenes name_auto should contain 'xylene': {row['name_auto']}"
    finally:
        conn.close()


def test_xylenes_auto_scores_cleared():
    """CAS 1330-20-7 (Xylenes) auto_* scores were contaminated from methanol and cleared.

    The original harvest incorrectly copied methanol's auto_* scores to the xylenes row.
    Since these scores are invalid, has_auto should be 0 and auto_* columns NULL.
    """
    import sqlite3
    from packages.p2oasys_core.lookup import default_lookup_db_path

    conn = sqlite3.connect(str(default_lookup_db_path()))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT has_expert, has_auto, auto_acute, auto_overall, auto_sources "
            "FROM by_cas WHERE cas = '1330-20-7'"
        ).fetchone()
        assert row is not None
        assert row["has_expert"] == 1, "Expert scores should remain valid"
        assert row["has_auto"] == 0, "Auto scores should be cleared (contaminated)"
        assert row["auto_acute"] is None, "auto_acute should be NULL"
        assert row["auto_overall"] is None, "auto_overall should be NULL"
        assert "contaminated" in (row["auto_sources"] or "").lower(), \
            "auto_sources should note contamination"
    finally:
        conn.close()
