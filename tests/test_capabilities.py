"""
Capability tests — one test per capability in capabilities.yaml.

Every capability must have a test that:
1. Runs on small offline fixtures (no network)
2. Proves it returns real values, not just imports
3. Optional/licensed capabilities: skip with explicit reason when not configured

Run with: pytest tests/test_capabilities.py -v
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path
from unittest import mock

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CAPABILITIES_YAML = REPO_ROOT / "capabilities.yaml"


def load_registry() -> dict:
    """Load capabilities.yaml."""
    with open(CAPABILITIES_YAML, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ─────────────────────────────────────────────────────────────────────────────
# Meta-tests: registry integrity
# ─────────────────────────────────────────────────────────────────────────────


def test_capabilities_yaml_exists():
    """capabilities.yaml must exist at repo root."""
    assert CAPABILITIES_YAML.is_file(), f"capabilities.yaml not found at {CAPABILITIES_YAML}"


def test_every_capability_has_test_id():
    """Every capability must have a test_id field."""
    registry = load_registry()
    capabilities = registry.get("capabilities", {})
    missing = []
    for cap_id, cap in capabilities.items():
        if not cap.get("test_id"):
            missing.append(cap_id)
    assert not missing, f"Capabilities missing test_id: {missing}"


def test_every_capability_has_module():
    """Every capability must have a module field."""
    registry = load_registry()
    capabilities = registry.get("capabilities", {})
    missing = []
    for cap_id, cap in capabilities.items():
        if not cap.get("module"):
            missing.append(cap_id)
    assert not missing, f"Capabilities missing module: {missing}"


def test_active_capability_modules_exist():
    """Active capabilities must have importable modules or existing files."""
    registry = load_registry()
    capabilities = registry.get("capabilities", {})
    missing = []
    for cap_id, cap in capabilities.items():
        if cap.get("status") not in ("active", "optional", "stub"):
            continue
        module = cap.get("module")
        if not module:
            continue
        try:
            importlib.import_module(module)
            continue
        except ImportError:
            pass
        parts = module.split(".")
        py_path = REPO_ROOT / "/".join(parts[:-1]) / f"{parts[-1]}.py"
        folder_path = REPO_ROOT / "/".join(parts)
        if py_path.is_file() or folder_path.is_dir() or (folder_path / "__init__.py").is_file():
            continue
        missing.append(f"{cap_id}: {module}")
    assert not missing, f"Active capability modules not found: {missing}"


def test_every_registry_entry_has_a_test():
    """Every capability test_id must correspond to a test function in this file."""
    registry = load_registry()
    capabilities = registry.get("capabilities", {})

    this_file = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(this_file)
    test_functions = {
        node.name for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    }

    missing = []
    for cap_id, cap in capabilities.items():
        test_id = cap.get("test_id", "")
        if "::" in test_id:
            test_name = test_id.split("::")[-1]
        else:
            test_name = test_id
        if test_name and test_name not in test_functions:
            missing.append(f"{cap_id}: {test_name}")

    assert not missing, f"Test functions missing for capabilities: {missing}"


# ─────────────────────────────────────────────────────────────────────────────
# PubChem capabilities
# ─────────────────────────────────────────────────────────────────────────────


def test_pubchem_pug_rest():
    """PubChem PUG-REST module loads and exports expected functions."""
    from packages.doss_core import pubchem

    assert hasattr(pubchem, "get_cid_by_cas")
    assert hasattr(pubchem, "get_compound_properties")
    assert hasattr(pubchem, "fetch_compound_data")
    assert hasattr(pubchem, "PubChemThrottledError")
    assert hasattr(pubchem, "_throttle")
    assert hasattr(pubchem, "_get_with_retries")

    assert pubchem._MIN_INTERVAL_S >= 0.1
    assert pubchem._MAX_RETRIES >= 1


def test_pubchem_pug_view_ghs():
    """PubChem PUG-View GHS extraction functions exist and parse correctly."""
    from packages.doss_core import pubchem

    assert hasattr(pubchem, "get_compound_view_data")
    assert hasattr(pubchem, "extract_experimental_properties")
    assert hasattr(pubchem, "_extract_ghs_hazards")
    assert hasattr(pubchem, "_extract_nfpa")

    ghs_section = {
        "Information": [
            {
                "Value": {
                    "StringWithMarkup": [
                        {"String": "H225 - Highly flammable liquid"}
                    ]
                }
            }
        ]
    }
    hazards = pubchem._extract_ghs_hazards(ghs_section)
    assert "H225" in hazards


def test_pubchem_ftp_bulk():
    """PubChem FTP bulk capability is TODO — test is a placeholder."""
    registry = load_registry()
    cap = registry["capabilities"]["pubchem_ftp_bulk"]
    assert cap["status"] == "TODO", "pubchem_ftp_bulk should be TODO until PR #7"
    pytest.skip("pubchem_ftp_bulk is TODO (PR #7)")


# ─────────────────────────────────────────────────────────────────────────────
# P2OASys capabilities
# ─────────────────────────────────────────────────────────────────────────────


def test_p2oasys_score_lookup():
    """P2OASys score lookup returns real scores from bundled SQLite."""
    from packages.p2oasys_core.lookup import (
        resolve_p2oasys,
        default_lookup_db_path,
        cas_catalog_count,
    )

    db_path = default_lookup_db_path()
    if not db_path.is_file():
        pytest.skip(f"P2OASys SQLite not found: {db_path}")

    count = cas_catalog_count()
    assert count > 100, f"Expected >100 CAS in catalog, got {count}"

    result = resolve_p2oasys("67-64-1", expert_df=None)
    assert result["overall"] != "-", "Acetone should have a P2OASys score"
    assert result["source"] in ("expert", "auto"), f"Unexpected source: {result['source']}"


def test_p2oasys_matrix_scorer():
    """P2OASys matrix scorer is TODO."""
    registry = load_registry()
    cap = registry["capabilities"]["p2oasys_matrix_scorer"]
    assert cap["status"] == "TODO", "p2oasys_matrix_scorer should be TODO until PR #8"
    pytest.skip("p2oasys_matrix_scorer is TODO (PR #8)")


# ─────────────────────────────────────────────────────────────────────────────
# SDS enrichment capabilities
# ─────────────────────────────────────────────────────────────────────────────


def test_fisher_sds_enrich():
    """Fisher SDS enrichment module loads and can parse SDS fields."""
    from packages.doss_core import fisher

    assert hasattr(fisher, "enrich_from_fisher")
    assert hasattr(fisher, "parse_sds_fields")
    assert hasattr(fisher, "sds_url")

    nfpa_text = """
    NFPA 704 Hazard Rating
    Health: 1  Flammability: 3  Instability: 0
    """
    fields = fisher.parse_sds_fields(nfpa_text)
    assert fields.get("nfpa_health") == "1"
    assert fields.get("nfpa_flame") == "3"


def test_tci_sds_enrich():
    """TCI SDS enrichment module loads and can parse SDS fields."""
    from packages.doss_core import tci

    assert hasattr(tci, "enrich_from_tci")
    assert hasattr(tci, "parse_sds_fields")
    assert hasattr(tci, "sds_url")

    nfpa_text = """
    HMIS Health: 2  Flammability: 4
    """
    fields = tci.parse_sds_fields(nfpa_text)
    assert fields.get("nfpa_health") == "2"
    assert fields.get("nfpa_flame") == "4"


def test_sigma_sds_enrich():
    """Sigma SDS enrichment is a stub — returns pending status."""
    from packages.doss_core import sigma

    assert hasattr(sigma, "enrich_from_sigma")

    result = sigma.enrich_from_sigma("67-64-1")
    assert result["ok"] is False
    assert "pending" in result.get("error", "").lower() or "stub" in result.get("error", "").lower()


# ─────────────────────────────────────────────────────────────────────────────
# HSPiP capabilities
# ─────────────────────────────────────────────────────────────────────────────


def test_hspip_sofx_lookup():
    """HSPiP sofx lookup module loads; skip if no data configured."""
    from packages.doss_core import hspip

    assert hasattr(hspip, "lookup_hspip")
    assert hasattr(hspip, "resolve_hspip_roots")
    assert hasattr(hspip, "load_sofx_by_cas")

    roots = hspip.resolve_hspip_roots()
    if not roots:
        pytest.skip("HSPiP data directory not configured (HSPIP_DATA) — optional/licensed")

    status = hspip.hspip_roots_status()
    assert status.get("available") is True
    assert status.get("cas_count", 0) > 0


def test_hspip_cli():
    """HSPiP CLI module loads; skip if not configured."""
    from packages.doss_core import hspip

    assert hasattr(hspip, "compute_hsp_via_cli")
    assert hasattr(hspip, "resolve_hspip_exe")

    exe_info = hspip.resolve_hspip_exe("")
    if not exe_info.get("ok"):
        pytest.skip("HSPiP.exe not configured (HSPIP_EXE) — optional/licensed")


def test_glove_hsp_screen():
    """Glove HSP polymer screening returns real classifications."""
    from packages.doss_core.glove_hsp import (
        classify_polymers,
        format_glove_hsp_flag,
        hansen_ra,
        GLOVE_POLYMER_HSP,
    )

    assert len(GLOVE_POLYMER_HSP) >= 6, "Expected at least 6 glove polymers"

    ra = hansen_ra(15.5, 6.0, 4.0, 17.5, 7.3, 6.5)
    assert 0 < ra < 20, f"Hansen Ra should be reasonable, got {ra}"

    result = classify_polymers(15.5, 10.2, 7.0)
    assert "incompatible" in result
    assert "should_not_dissolve" in result

    flag = format_glove_hsp_flag(solvent_d=15.5, solvent_p=10.2, solvent_h=7.0, known_glove=None)
    assert flag is not None
    assert "Unknown" in flag or "incompatible" in flag or "dissolve" in flag


# ─────────────────────────────────────────────────────────────────────────────
# Scorer reference tables (TODO)
# ─────────────────────────────────────────────────────────────────────────────


def test_cameo_nfpa_sqlite():
    """CAMEO NFPA sqlite is TODO."""
    registry = load_registry()
    cap = registry["capabilities"]["cameo_nfpa_sqlite"]
    assert cap["status"] == "TODO", "cameo_nfpa_sqlite should be TODO until PR #1"
    pytest.skip("cameo_nfpa_sqlite is TODO (PR #1)")


def test_iarc_table():
    """IARC table is TODO."""
    registry = load_registry()
    cap = registry["capabilities"]["iarc_table"]
    assert cap["status"] == "TODO", "iarc_table should be TODO until PR #8"
    pytest.skip("iarc_table is TODO (PR #8)")


def test_odp_gwp_ipcc():
    """ODP/GWP/IPCC tables are TODO."""
    registry = load_registry()
    cap = registry["capabilities"]["odp_gwp_ipcc"]
    assert cap["status"] == "TODO", "odp_gwp_ipcc should be TODO until PR #8"
    pytest.skip("odp_gwp_ipcc is TODO (PR #8)")


def test_caa_hap_list():
    """CAA HAP list is TODO."""
    registry = load_registry()
    cap = registry["capabilities"]["caa_hap_list"]
    assert cap["status"] == "TODO", "caa_hap_list should be TODO until PR #8"
    pytest.skip("caa_hap_list is TODO (PR #8)")


# ─────────────────────────────────────────────────────────────────────────────
# External tools (TODO/optional)
# ─────────────────────────────────────────────────────────────────────────────


def test_ecosar_pyepisuite():
    """ECOSAR/pyepisuite is TODO."""
    registry = load_registry()
    cap = registry["capabilities"]["ecosar_pyepisuite"]
    assert cap["status"] == "TODO", "ecosar_pyepisuite should be TODO until PR #6"
    pytest.skip("ecosar_pyepisuite is TODO (PR #6)")


def test_iuclid_dossiers():
    """IUCLID dossiers is TODO."""
    registry = load_registry()
    cap = registry["capabilities"]["iuclid_dossiers"]
    assert cap["status"] == "TODO", "iuclid_dossiers should be TODO until PR #9"
    pytest.skip("iuclid_dossiers is TODO (PR #9)")


# ─────────────────────────────────────────────────────────────────────────────
# Core application
# ─────────────────────────────────────────────────────────────────────────────


def test_doss_app():
    """DoSS app module loads and exports expected functions."""
    import ast

    app_path = REPO_ROOT / "apps" / "doss_ondemand" / "app.py"
    assert app_path.is_file(), f"DoSS app not found at {app_path}"

    tree = ast.parse(app_path.read_text(encoding="utf-8"), filename=str(app_path))
    function_names = {
        node.name for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
    }
    assert "main" in function_names, "DoSS app should have main()"
    assert "build_doss_row" in function_names, "DoSS app should have build_doss_row()"


def test_assess_spine():
    """assess() spine is TODO."""
    registry = load_registry()
    cap = registry["capabilities"]["assess_spine"]
    assert cap["status"] == "TODO", "assess_spine should be TODO until PR #5"
    pytest.skip("assess_spine is TODO (PR #5)")


# ─────────────────────────────────────────────────────────────────────────────
# Capability config module
# ─────────────────────────────────────────────────────────────────────────────


def test_capability_config_loads():
    """capability_config module loads and provides expected config classes."""
    from packages import capability_config

    assert hasattr(capability_config, "REPO_ROOT")
    assert hasattr(capability_config, "DATA_DIR")
    assert hasattr(capability_config, "PubChemConfig")
    assert hasattr(capability_config, "P2OASysConfig")
    assert hasattr(capability_config, "HSPiPConfig")
    assert hasattr(capability_config, "SDSEnrichConfig")
    assert hasattr(capability_config, "ScorerConfig")
    assert hasattr(capability_config, "ExternalToolsConfig")
    assert hasattr(capability_config, "get_all_config")

    config = capability_config.get_all_config()
    assert "repo_root" in config
    assert "pubchem" in config
    assert "p2oasys" in config


def test_capability_report_runs():
    """capability_report module loads and generates a report."""
    from packages import capability_report

    assert hasattr(capability_report, "capability_report")
    assert hasattr(capability_report, "format_report")
    assert hasattr(capability_report, "log_capability_summary")

    results = capability_report.capability_report()
    assert len(results) > 0, "Expected at least one capability in report"

    output = capability_report.format_report(results)
    assert "Capability Report" in output
    assert "ACTIVE" in output or "TODO" in output


# ─────────────────────────────────────────────────────────────────────────────
# GHaz7/GHaz8 stack capabilities
# ─────────────────────────────────────────────────────────────────────────────


def test_comptox_dsstox_lookup():
    """CompTox/DSSTox lookup is TODO."""
    registry = load_registry()
    cap = registry["capabilities"]["comptox_dsstox_lookup"]
    assert cap["status"] == "TODO", "comptox_dsstox_lookup should be TODO until PR #8"
    pytest.skip("comptox_dsstox_lookup is TODO (PR #8)")


def test_toxval_lookup():
    """ToxVal/ToxValDB lookup is TODO."""
    registry = load_registry()
    cap = registry["capabilities"]["toxval_lookup"]
    assert cap["status"] == "TODO", "toxval_lookup should be TODO until PR #8"
    pytest.skip("toxval_lookup is TODO (PR #8)")


def test_opera_predictions():
    """OPERA predictions is TODO."""
    registry = load_registry()
    cap = registry["capabilities"]["opera_predictions"]
    assert cap["status"] == "TODO", "opera_predictions should be TODO until PR #8"
    pytest.skip("opera_predictions is TODO (PR #8)")


def test_ghaz7_headless_cli():
    """GHaz7 headless CLI is MISSING (needs re-rooting)."""
    registry = load_registry()
    cap = registry["capabilities"]["ghaz7_headless_cli"]
    assert cap["status"] == "MISSING", "ghaz7_headless_cli should be MISSING"
    pytest.skip("ghaz7_headless_cli is MISSING (needs layout adaptation)")


def test_fast_p2oasys_batch():
    """fast P2OASys v2 batch is TODO."""
    registry = load_registry()
    cap = registry["capabilities"]["fast_p2oasys_batch"]
    assert cap["status"] == "TODO", "fast_p2oasys_batch should be TODO until PR #8"
    pytest.skip("fast_p2oasys_batch is TODO (PR #8)")


# ─────────────────────────────────────────────────────────────────────────────
# Scorer fixes (PR #10)
# ─────────────────────────────────────────────────────────────────────────────


def test_scorer_beyond_solubility():
    """Scorer beyond-solubility checks is TODO."""
    registry = load_registry()
    cap = registry["capabilities"]["scorer_beyond_solubility"]
    assert cap["status"] == "TODO", "scorer_beyond_solubility should be TODO until PR #10"
    pytest.skip("scorer_beyond_solubility is TODO (PR #10)")


def test_scorer_suspicious_input():
    """Scorer suspicious input checks is TODO."""
    registry = load_registry()
    cap = registry["capabilities"]["scorer_suspicious_input"]
    assert cap["status"] == "TODO", "scorer_suspicious_input should be TODO until PR #10"
    pytest.skip("scorer_suspicious_input is TODO (PR #10)")


def test_scorer_unit_conversion():
    """Scorer unit conversion hardening is TODO."""
    registry = load_registry()
    cap = registry["capabilities"]["scorer_unit_conversion"]
    assert cap["status"] == "TODO", "scorer_unit_conversion should be TODO until PR #10"
    pytest.skip("scorer_unit_conversion is TODO (PR #10)")
