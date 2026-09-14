"""Bundled harvest/auto P2OASys sqlite is visible to DoSS without a sibling GHaz7 tree."""
from __future__ import annotations

from packages.p2oasys_core.lookup import (
    default_lookup_db_path,
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
