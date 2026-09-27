"""
Capability report: print status of all capabilities at startup or on demand.

Usage:
    python -m packages.capability_report

Output shows ACTIVE, DISABLED, or MISSING_DATA for each capability,
along with the reason and env var to set for configuration.
"""

from __future__ import annotations

import importlib
import logging
import sys
from pathlib import Path
from typing import Any

import yaml

from packages.capability_config import (
    REPO_ROOT,
    HSPiPConfig,
    P2OASysConfig,
    PubChemConfig,
    ScorerConfig,
    SDSEnrichConfig,
    ExternalToolsConfig,
)

logger = logging.getLogger(__name__)

# Status constants
STATUS_ACTIVE = "ACTIVE"
STATUS_DISABLED = "DISABLED"
STATUS_MISSING_DATA = "MISSING_DATA"
STATUS_TODO = "TODO"
STATUS_STUB = "STUB"
STATUS_OPTIONAL_SKIP = "OPTIONAL_SKIP"


def load_registry() -> dict[str, Any]:
    """Load capabilities.yaml registry."""
    registry_path = REPO_ROOT / "capabilities.yaml"
    if not registry_path.is_file():
        logger.warning("capabilities.yaml not found at %s", registry_path)
        return {"capabilities": {}}
    with open(registry_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {"capabilities": {}}


def check_module_exists(module_path: str) -> bool:
    """Check if a module can be imported or file exists."""
    try:
        importlib.import_module(module_path)
        return True
    except ImportError:
        pass

    parts = module_path.split(".")
    py_path = REPO_ROOT / "/".join(parts[:-1]) / f"{parts[-1]}.py"
    if py_path.is_file():
        return True
    init_path = REPO_ROOT / "/".join(parts) / "__init__.py"
    if init_path.is_file():
        return True
    folder_path = REPO_ROOT / "/".join(parts)
    if folder_path.is_dir():
        return True
    return False


def check_capability_status(cap_id: str, cap: dict[str, Any]) -> dict[str, Any]:
    """
    Check status of a single capability.

    Returns dict with:
        status: ACTIVE | DISABLED | MISSING_DATA | TODO | STUB | OPTIONAL_SKIP
        reason: Human-readable explanation
        env_hint: Env var to set (if applicable)
    """
    result: dict[str, Any] = {
        "id": cap_id,
        "name": cap.get("name", cap_id),
        "status": STATUS_ACTIVE,
        "reason": "",
        "env_hint": None,
        "module": cap.get("module"),
        "required": cap.get("required", False),
        "licensed": cap.get("licensed", False),
    }

    yaml_status = cap.get("status", "active")

    if yaml_status == "TODO":
        pr = cap.get("pr", "")
        result["status"] = STATUS_TODO
        result["reason"] = f"Planned in {pr}" if pr else "Planned"
        return result

    if yaml_status == "stub":
        result["status"] = STATUS_STUB
        result["reason"] = "Module exists but feature not functional"
        return result

    module = cap.get("module")
    if module and not check_module_exists(module):
        result["status"] = STATUS_MISSING_DATA
        result["reason"] = f"Module not found: {module}"
        return result

    if cap_id == "pubchem_pug_rest":
        result["status"] = STATUS_ACTIVE
        result["reason"] = f"Rate limit: {PubChemConfig.min_interval_s()}s, max retries: {PubChemConfig.max_retries()}"

    elif cap_id == "pubchem_pug_view_ghs":
        result["status"] = STATUS_ACTIVE
        result["reason"] = "GHS/NFPA extraction from PUG View"

    elif cap_id == "pubchem_ftp_bulk":
        bulk_dir = PubChemConfig.bulk_dir()
        if PubChemConfig.bulk_disabled():
            result["status"] = STATUS_DISABLED
            result["reason"] = "Disabled via PUBCHEM_DISABLE_BULK"
        elif not bulk_dir or not bulk_dir.is_dir():
            result["status"] = STATUS_MISSING_DATA
            result["reason"] = "Bulk directory not configured"
            result["env_hint"] = "PUBCHEM_BULK_DIR"
        else:
            result["status"] = STATUS_ACTIVE
            result["reason"] = f"Bulk dir: {bulk_dir}"

    elif cap_id == "p2oasys_score_lookup":
        db_path = P2OASysConfig.score_lookup_db()
        if db_path.is_file():
            result["status"] = STATUS_ACTIVE
            result["reason"] = f"SQLite: {db_path.name}"
        else:
            result["status"] = STATUS_MISSING_DATA
            result["reason"] = f"Database not found: {db_path}"
            result["env_hint"] = "P2OASYS_SCORE_LOOKUP_DB"

    elif cap_id == "p2oasys_matrix_scorer":
        matrix_dir = P2OASysConfig.matrix_dir()
        if not matrix_dir or not matrix_dir.is_dir():
            result["status"] = STATUS_MISSING_DATA
            result["reason"] = "Matrix directory not configured"
            result["env_hint"] = "P2OASYS_MATRIX_DIR"
        else:
            result["status"] = STATUS_ACTIVE
            result["reason"] = f"Matrix dir: {matrix_dir}"

    elif cap_id == "fisher_sds_enrich":
        if SDSEnrichConfig.fisher_enabled():
            result["status"] = STATUS_ACTIVE
            result["reason"] = "Fisher enrichment enabled (default)"
        else:
            result["status"] = STATUS_DISABLED
            result["reason"] = "Disabled via DOSS_ENABLE_FISHER=0"
            result["env_hint"] = "DOSS_ENABLE_FISHER"

    elif cap_id == "tci_sds_enrich":
        result["status"] = STATUS_ACTIVE
        result["reason"] = "TCI enrichment always available"

    elif cap_id == "sigma_sds_enrich":
        result["status"] = STATUS_STUB
        result["reason"] = "MilliporeSigma API access pending"

    elif cap_id == "hspip_sofx_lookup":
        data_dir = HSPiPConfig.data_dir() or HSPiPConfig.teams_data_dir()
        if data_dir and data_dir.is_dir():
            sofx_count = sum(1 for _ in data_dir.rglob("*.sofx"))
            result["status"] = STATUS_ACTIVE
            result["reason"] = f"{sofx_count} .sofx files in {data_dir.name}"
        else:
            result["status"] = STATUS_OPTIONAL_SKIP
            result["reason"] = "HSPiP data directory not configured (licensed)"
            result["env_hint"] = "HSPIP_DATA"

    elif cap_id == "hspip_cli":
        exe_path = HSPiPConfig.exe_path() or HSPiPConfig.teams_exe_dir()
        if exe_path:
            p = Path(exe_path)
            if p.is_file() and p.name.lower() == "hspip.exe":
                result["status"] = STATUS_ACTIVE
                result["reason"] = f"HSPiP.exe: {p}"
            elif p.is_dir() and (p / "HSPiP.exe").is_file():
                result["status"] = STATUS_ACTIVE
                result["reason"] = f"HSPiP.exe: {p / 'HSPiP.exe'}"
            else:
                result["status"] = STATUS_OPTIONAL_SKIP
                result["reason"] = f"HSPiP.exe not found at {exe_path}"
                result["env_hint"] = "HSPIP_EXE"
        else:
            result["status"] = STATUS_OPTIONAL_SKIP
            result["reason"] = "HSPiP.exe path not configured (licensed)"
            result["env_hint"] = "HSPIP_EXE"

    elif cap_id == "glove_hsp_screen":
        result["status"] = STATUS_ACTIVE
        result["reason"] = "HSP glove polymer screening available"

    elif cap_id == "cameo_nfpa_sqlite":
        db_path = ScorerConfig.cameo_nfpa_db()
        if db_path and db_path.is_file():
            result["status"] = STATUS_ACTIVE
            result["reason"] = f"CAMEO NFPA: {db_path.name}"
        else:
            result["status"] = STATUS_MISSING_DATA
            result["reason"] = "CAMEO NFPA database not configured"
            result["env_hint"] = "CAMEO_NFPA_DB"

    elif cap_id == "iarc_table":
        table_path = ScorerConfig.iarc_table()
        if table_path and table_path.is_file():
            result["status"] = STATUS_ACTIVE
            result["reason"] = f"IARC table: {table_path.name}"
        else:
            result["status"] = STATUS_MISSING_DATA
            result["reason"] = "IARC table not configured"
            result["env_hint"] = "IARC_TABLE_PATH"

    elif cap_id == "odp_gwp_ipcc":
        table_path = ScorerConfig.odp_gwp_table()
        if table_path and table_path.is_file():
            result["status"] = STATUS_ACTIVE
            result["reason"] = f"ODP/GWP table: {table_path.name}"
        else:
            result["status"] = STATUS_MISSING_DATA
            result["reason"] = "ODP/GWP table not configured"
            result["env_hint"] = "ODP_GWP_TABLE_PATH"

    elif cap_id == "caa_hap_list":
        list_path = ScorerConfig.caa_hap_list()
        if list_path and list_path.is_file():
            result["status"] = STATUS_ACTIVE
            result["reason"] = f"CAA HAP list: {list_path.name}"
        else:
            result["status"] = STATUS_MISSING_DATA
            result["reason"] = "CAA HAP list not configured"
            result["env_hint"] = "CAA_HAP_LIST_PATH"

    elif cap_id == "ecosar_pyepisuite":
        if ExternalToolsConfig.ecosar_disabled():
            result["status"] = STATUS_DISABLED
            result["reason"] = "Disabled via ECOSAR_DISABLE=1"
        elif ExternalToolsConfig.episuite_path():
            result["status"] = STATUS_ACTIVE
            result["reason"] = f"EPI Suite: {ExternalToolsConfig.episuite_path()}"
        else:
            result["status"] = STATUS_OPTIONAL_SKIP
            result["reason"] = "EPI Suite path not configured (licensed)"
            result["env_hint"] = "EPISUITE_PATH"

    elif cap_id == "iuclid_dossiers":
        if ExternalToolsConfig.iuclid_api_url() and ExternalToolsConfig.iuclid_api_key():
            result["status"] = STATUS_ACTIVE
            result["reason"] = f"IUCLID API: {ExternalToolsConfig.iuclid_api_url()}"
        else:
            result["status"] = STATUS_MISSING_DATA
            result["reason"] = "IUCLID API credentials not configured"
            result["env_hint"] = "IUCLID_API_URL, IUCLID_API_KEY"

    elif cap_id == "doss_app":
        app_path = REPO_ROOT / "apps" / "doss_ondemand" / "app.py"
        if app_path.is_file():
            result["status"] = STATUS_ACTIVE
            result["reason"] = "DoSS Streamlit app available"
        else:
            result["status"] = STATUS_MISSING_DATA
            result["reason"] = f"DoSS app not found: {app_path}"

    elif cap_id == "assess_spine":
        result["status"] = STATUS_TODO
        result["reason"] = "Planned in PR #5"

    return result


def capability_report() -> list[dict[str, Any]]:
    """Generate capability report for all registered capabilities."""
    registry = load_registry()
    capabilities = registry.get("capabilities", {})

    results = []
    for cap_id, cap in capabilities.items():
        result = check_capability_status(cap_id, cap)
        results.append(result)

    return results


def format_report(results: list[dict[str, Any]], *, verbose: bool = False) -> str:
    """Format capability report for console output."""
    lines = []
    lines.append("=" * 72)
    lines.append("TURI Safe Chem DB — Capability Report")
    lines.append("=" * 72)
    lines.append("")

    active = [r for r in results if r["status"] == STATUS_ACTIVE]
    disabled = [r for r in results if r["status"] == STATUS_DISABLED]
    missing = [r for r in results if r["status"] == STATUS_MISSING_DATA]
    optional_skip = [r for r in results if r["status"] == STATUS_OPTIONAL_SKIP]
    todo = [r for r in results if r["status"] == STATUS_TODO]
    stub = [r for r in results if r["status"] == STATUS_STUB]

    status_icon = {
        STATUS_ACTIVE: "✅",
        STATUS_DISABLED: "⛔",
        STATUS_MISSING_DATA: "❌",
        STATUS_OPTIONAL_SKIP: "🔶",
        STATUS_TODO: "📝",
        STATUS_STUB: "⬜",
    }

    for r in results:
        icon = status_icon.get(r["status"], "?")
        name = r["name"]
        status = r["status"]
        reason = r["reason"]
        line = f"{icon} [{status:14}] {name}"
        if verbose or status != STATUS_ACTIVE:
            line += f"\n   └─ {reason}"
            if r.get("env_hint"):
                line += f"\n   └─ Set: {r['env_hint']}"
        lines.append(line)

    lines.append("")
    lines.append("-" * 72)
    lines.append("Summary:")
    lines.append(f"  ✅ ACTIVE:        {len(active)}")
    lines.append(f"  🔶 OPTIONAL_SKIP: {len(optional_skip)} (licensed/optional, not configured)")
    lines.append(f"  ⛔ DISABLED:      {len(disabled)}")
    lines.append(f"  ❌ MISSING_DATA:  {len(missing)}")
    lines.append(f"  📝 TODO:          {len(todo)}")
    lines.append(f"  ⬜ STUB:          {len(stub)}")
    lines.append("-" * 72)

    if missing:
        lines.append("")
        lines.append("⚠️  Missing data — set these env vars to enable:")
        for r in missing:
            if r.get("env_hint"):
                lines.append(f"   {r['name']}: {r['env_hint']}")

    return "\n".join(lines)


def log_capability_summary(*, logger_instance: logging.Logger | None = None) -> None:
    """Log a brief capability summary at startup."""
    log = logger_instance or logger
    results = capability_report()

    active = sum(1 for r in results if r["status"] == STATUS_ACTIVE)
    total = len(results)
    missing = [r for r in results if r["status"] == STATUS_MISSING_DATA]

    log.info("Capabilities: %d/%d active", active, total)
    for r in missing:
        log.warning(
            "Capability missing data: %s — set %s",
            r["name"],
            r.get("env_hint", "(see capabilities.yaml)"),
        )


def main() -> None:
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="TURI Safe Chem DB capability report",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show reasons for all capabilities (not just issues)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )
    args = parser.parse_args()

    results = capability_report()

    if args.json:
        import json
        print(json.dumps(results, indent=2, default=str))
    else:
        print(format_report(results, verbose=args.verbose))


if __name__ == "__main__":
    main()
