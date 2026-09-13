"""Smoke tests for package importability (no network)."""
from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_key_modules_parse():
    paths = [
        REPO / "apps/doss_ondemand/app.py",
        REPO / "packages/doss_core/tci.py",
        REPO / "packages/doss_core/fisher.py",
        REPO / "packages/doss_core/hspip.py",
        REPO / "packages/p2oasys_core/lookup.py",
    ]
    for p in paths:
        ast.parse(p.read_text(encoding="utf-8"), filename=str(p))


def test_import_packages():
    import packages.doss_core.tci as tci
    import packages.doss_core.fisher as fisher
    import packages.p2oasys_core.lookup as lookup

    assert hasattr(tci, "enrich_from_tci")
    assert hasattr(fisher, "enrich_from_fisher")
    assert hasattr(lookup, "resolve_p2oasys")
