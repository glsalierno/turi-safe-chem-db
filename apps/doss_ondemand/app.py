"""
DoSS on-demand: Database of Safer Solvents row generator.

Generates DoSS-shaped rows matching TURI's DoSS export format from CAS numbers
using PubChem, expert/auto P2OASys caches, and on-demand Fisher/TCI SDS enrichment.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

from packages.doss_core.schema import (
    DOSS_COLUMNS,
    EMPTY_VALUE,
    HSP_PLACEHOLDER,
    coverage_report,
    empty_row,
    format_row_for_csv,
)
from packages.p2oasys_core.lookup import (
    DEFAULT_EXPERT_CSV,
    documented_paths,
    default_lookup_db_path,
    load_expert_csv,
    resolve_p2oasys,
)
from packages.doss_core.pubchem import (
    PubChemError,
    fetch_compound_data,
    get_smiles_for_cas,
    parse_numeric_with_unit,
)
from packages.doss_core.sigma import enrich_from_sigma
from packages.doss_core.tci import enrich_from_tci
from packages.doss_core.fisher import enrich_from_fisher
from packages.doss_core.hspip import (
    apply_runtime_hspip_env,
    compute_hsp_via_cli,
    default_hspip_data_raw,
    default_hspip_exe_raw,
    hspip_roots_status,
    lookup_hspip,
    resolve_hspip_data,
    resolve_hspip_exe,
    save_hspip_paths,
)
from packages.doss_core.glove_hsp import format_glove_hsp_flag
from packages.doss_core.ecosar import ecosar_available, summarize_ecosar_for_cas

st.set_page_config(
    page_title="TURI Safe Chem DB - DoSS",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .main .block-container {
        max-width: 100%;
        padding-left: 2rem;
        padding-right: 2rem;
    }
    .coverage-filled { color: #28a745; }
    .coverage-empty { color: #dc3545; }
    .coverage-placeholder { color: #ffc107; }
    </style>
    """,
    unsafe_allow_html=True,
)


def _precautionary_nfpa(candidates):
    """Pick higher NFPA rating (0-4); return (value_str, source_note)."""
    scored = []
    for val, src in candidates:
        if val is None or val == "":
            continue
        try:
            n = int(str(val).strip()[0])
        except (ValueError, TypeError, IndexError):
            continue
        if 0 <= n <= 4:
            scored.append((n, str(src)))
    if not scored:
        return None, None
    max_n = max(n for n, _ in scored)
    parts = [f"{src}={n}" for n, src in scored]
    if len({n for n, _ in scored}) > 1:
        note = f"precautionary max {max_n} ({', '.join(parts)})"
    else:
        note = scored[0][1]
    return str(max_n), note


def _cost_per_kg_from_per_g(per_g):
    try:
        return float(per_g) * 1000.0
    except (TypeError, ValueError):
        return None


GLOVE_MAP = {
    "67-64-1": "Nitrile",
    "64-17-5": "Nitrile",
    "67-56-1": "Nitrile",
    "71-43-2": "Viton",
    "108-88-3": "Nitrile/Viton",
    "67-66-3": "Viton",
    "75-09-2": "Viton",
    "110-54-3": "Nitrile",
    "142-82-5": "Nitrile",
}

PHYS_COLS = {
    "boiling_point_c": "Boiling Point (C)",
    "melting_point_c": "Melting Point (C)",
    "flash_point_c": "Flash Point (C)",
    "density_g_l": "Density (g/L)",
    "vapor_pressure_mmhg": "Vapor Pressure (mmHg)",
    "viscosity_cp": "Viscosity (cP)",
}


def _fmt_num(val: float, digits: int = 1) -> str:
    return str(round(float(val), digits))




def render_hspip_setup_sidebar() -> dict:
    """Sidebar: due-diligence + persistable HSPiP.exe / sofx data paths."""
    st.sidebar.markdown("## HSPiP setup")
    st.sidebar.caption(
        "Optional. Install HSPiP yourself from [hansen-solubility.com](https://www.hansen-solubility.com). "
        "This app never ships the binary. Close the HSPiP desktop app before using the CLI."
    )

    if "hspip_exe_raw" not in st.session_state:
        st.session_state["hspip_exe_raw"] = default_hspip_exe_raw()
    if "hspip_data_raw" not in st.session_state:
        st.session_state["hspip_data_raw"] = default_hspip_data_raw()

    exe_raw = st.sidebar.text_input(
        "Where is HSPiP installed on this PC?",
        key="hspip_exe_raw",
        help="Folder with HSPiP.exe, or the full path to HSPiP.exe. Honors HSPIP_PATH / HSPIP_EXE. Saved locally.",
    )
    data_raw = st.sidebar.text_input(
        "Where are the HSPiP data files (.sofx)?",
        key="hspip_data_raw",
        help="Folder of licensed .sofx libraries. Default: HSPIP_DATA env or Teams pack HSPiP_Data.",
    )

    save_hspip_paths(exe_raw or "", data_raw or "")
    apply_runtime_hspip_env(exe_raw or "", data_raw or "")

    exe_info = resolve_hspip_exe(exe_raw or "")
    data_info = resolve_hspip_data(data_raw or "")
    if exe_info.get("ok"):
        st.sidebar.markdown(f"✅ `{exe_info['exe']}`")
    else:
        st.sidebar.markdown(f"❌ {exe_info.get('message', 'HSPiP.exe not set')}")
    if data_info.get("ok"):
        st.sidebar.markdown(f"✅ {data_info.get('message')}")
    else:
        st.sidebar.markdown(f"❌ {data_info.get('message')}")

    hsp_status = hspip_roots_status()
    if hsp_status.get("available"):
        st.sidebar.caption(
            f"HSPiP sofx: {hsp_status['cas_count']} CAS indexed "
            f"({len(hsp_status['roots'])} data root(s))"
        )
    else:
        st.sidebar.warning("HSPiP data folder not found — D/P/H stay needs_HSPiP (that is OK for basic lookups)")

    # CLI auto-run stays available but is less prominent (advanced users)
    auto_cli = st.sidebar.checkbox(
        "Auto-run CLI when CAS misses sofx",
        value=False,
        help="OFF by default (safer). Close the HSPiP GUI first. Never invents D/P/H.",
    )
    return {"exe_info": exe_info, "data_info": data_info, "auto_cli": auto_cli}


def apply_cli_hsp_to_row(row: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    """Fill D/P/H from a successful CLI parse only. Never invents."""
    if not result.get("ok"):
        err = result.get("error") or "CLI failed"
        notes = list(row.get("_enrich_notes") or [])
        notes.append(f"HSPiP CLI: {err}")
        row["_enrich_notes"] = notes
        return row
    try:
        d = float(result["D"])
        p = float(result["P"])
        h = float(result["H"])
    except (KeyError, TypeError, ValueError):
        notes = list(row.get("_enrich_notes") or [])
        notes.append("HSPiP CLI: incomplete D/P/H in result; not inventing values")
        row["_enrich_notes"] = notes
        return row
    src = result.get("source_label") or "HSPiP CLI Y-MBSX"
    row["D"] = str(d)
    row["P"] = str(p)
    row["H"] = str(h)
    prop_sources = dict(row.get("_prop_sources") or {})
    prop_sources["D"] = src
    prop_sources["P"] = src
    prop_sources["H"] = src
    if result.get("RER") is not None:
        row["RER (HSP)"] = str(result["RER"])
        prop_sources["RER (HSP)"] = src
    row["_prop_sources"] = prop_sources
    notes = list(row.get("_enrich_notes") or [])
    notes.append(f"HSPiP CLI: {src}")
    row["_enrich_notes"] = notes
    return row


def run_cli_for_row(row: Dict[str, Any], exe_info: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve SMILES (row / session / PubChem) then call HSPiP CLI. Never invents D/P/H."""
    if not exe_info.get("ok") or exe_info.get("exe") is None:
        return {"ok": False, "error": "Provide a valid HSPiP.exe path above first."}
    cas = str(row.get("CAS") or "").strip()
    smiles = (
        str(row.get("_smiles") or "").strip()
        or str(st.session_state.get("current_smiles") or "").strip()
    )
    if not smiles and cas:
        try:
            smiles = get_smiles_for_cas(cas) or ""
        except PubChemError as exc:
            return {"ok": False, "error": f"PubChem SMILES lookup failed: {exc}"}
    if not smiles:
        return {"ok": False, "error": "No SMILES available. Cannot invent D/P/H."}
    st.session_state["current_smiles"] = smiles
    row["_smiles"] = smiles
    return compute_hsp_via_cli(smiles, exe_info["exe"])



def build_doss_row(
    pubchem_data: Dict[str, Any],
    expert_df: Optional[pd.DataFrame] = None,
    *,
    enable_tci: bool = True,
    enable_fisher: bool = True,
    enable_ecosar: bool = False,
) -> Dict[str, Any]:
    """Convert PubChem (+ optional Fisher/TCI) data to a DoSS row."""
    row = empty_row()
    prop_sources: Dict[str, str] = {}
    notes: List[str] = []

    cas = pubchem_data.get("cas", "")
    props = pubchem_data.get("properties", {})

    row["CAS"] = cas
    row["Solvent Name"] = pubchem_data.get("name", EMPTY_VALUE)
    row["Formula"] = pubchem_data.get("formula", EMPTY_VALUE)

    mw = pubchem_data.get("molecular_weight")
    if mw is not None:
        row["Molecular Weight"] = str(round(float(mw), 2))
        prop_sources["Molecular Weight"] = "PubChem"

    row["D"] = HSP_PLACEHOLDER
    row["P"] = HSP_PLACEHOLDER
    row["H"] = HSP_PLACEHOLDER
    row["RER (HSP)"] = HSP_PLACEHOLDER
    row["_smiles"] = pubchem_data.get("smiles") or ""

    # --- HSPiP local sofx (never invent) ---
    solvent_d = solvent_p = solvent_h = None
    hsp = lookup_hspip(cas)
    if hsp:
        solvent_d, solvent_p, solvent_h = hsp["D"], hsp["P"], hsp["H"]
        row["D"] = str(hsp["D"])
        row["P"] = str(hsp["P"])
        row["H"] = str(hsp["H"])
        src_label = hsp["source_label"]
        prop_sources["D"] = src_label
        prop_sources["P"] = src_label
        prop_sources["H"] = src_label
        if hsp.get("RER") is not None:
            row["RER (HSP)"] = str(hsp["RER"])
            prop_sources["RER (HSP)"] = src_label
        notes.append(f"HSPiP: {src_label}")

    # --- PubChem physchem baseline ---
    bp = props.get("Boiling Point")
    if bp:
        bp_val = parse_numeric_with_unit(bp)
        if bp_val is not None:
            row["Boiling Point (C)"] = _fmt_num(bp_val, 1)
            prop_sources["Boiling Point (C)"] = "PubChem"

    mp = props.get("Melting Point")
    if mp:
        mp_val = parse_numeric_with_unit(mp)
        if mp_val is not None:
            row["Melting Point (C)"] = _fmt_num(mp_val, 1)
            prop_sources["Melting Point (C)"] = "PubChem"

    fp = props.get("Flash Point")
    if fp:
        fp_val = parse_numeric_with_unit(fp)
        if fp_val is not None:
            row["Flash Point (C)"] = _fmt_num(fp_val, 1)
            prop_sources["Flash Point (C)"] = "PubChem"

    density = props.get("Density")
    if density:
        d_val = parse_numeric_with_unit(density)
        if d_val is not None:
            if d_val < 20:
                d_val = d_val * 1000
            row["Density (g/L)"] = _fmt_num(d_val, 1)
            prop_sources["Density (g/L)"] = "PubChem"

    vp = props.get("Vapor Pressure")
    if vp:
        vp_val = parse_numeric_with_unit(vp)
        if vp_val is not None:
            row["Vapor Pressure (mmHg)"] = _fmt_num(vp_val, 2)
            prop_sources["Vapor Pressure (mmHg)"] = "PubChem"

    visc = props.get("Viscosity")
    if visc:
        visc_val = parse_numeric_with_unit(visc)
        if visc_val is not None:
            row["Viscosity (cP)"] = _fmt_num(visc_val, 3)
            prop_sources["Viscosity (cP)"] = "PubChem"

    ri = props.get("Refractive Index")
    if ri:
        ri_val = parse_numeric_with_unit(ri)
        if ri_val is not None:
            row["Refractive Index"] = _fmt_num(ri_val, 4)
            prop_sources["Refractive Index"] = "PubChem"

    sol = props.get("Solubility")
    if sol:
        sol_str = str(sol).lower()
        if "miscible" in sol_str or "infinite" in sol_str:
            row["Water Solubility (g/L)"] = "miscible"
            prop_sources["Water Solubility (g/L)"] = "PubChem"
        elif "insoluble" in sol_str or "immiscible" in sol_str:
            row["Water Solubility (g/L)"] = "insoluble"
            prop_sources["Water Solubility (g/L)"] = "PubChem"
        else:
            sol_val = parse_numeric_with_unit(sol)
            if sol_val is not None:
                row["Water Solubility (g/L)"] = _fmt_num(sol_val, 2)
                prop_sources["Water Solubility (g/L)"] = "PubChem"

    # --- PubChem NFPA / GHS baseline (merged precautionary with vendor SDS below) ---
    nfpa_health_cands = []
    nfpa_flame_cands = []
    nfpa_health = pubchem_data.get("nfpa_health")
    nfpa_flame = pubchem_data.get("nfpa_flame")
    if nfpa_health:
        nfpa_health_cands.append((nfpa_health, "PubChem"))
    if nfpa_flame:
        nfpa_flame_cands.append((nfpa_flame, "PubChem"))

    ghs = pubchem_data.get("ghs_hazards", [])
    row["GHS Hazards"] = ", ".join(ghs) if ghs else EMPTY_VALUE
    if ghs:
        prop_sources["GHS Hazards"] = "PubChem"

    curated_glove = GLOVE_MAP.get(cas)
    row["Glove Type"] = curated_glove if curated_glove else "Unknown"
    if curated_glove:
        prop_sources["Glove Type"] = "curated map"
    row["SDS Link"] = pubchem_data.get("pubchem_url", EMPTY_VALUE)
    if row["SDS Link"] not in (EMPTY_VALUE, ""):
        prop_sources["SDS Link"] = "PubChem"

    row["Lab Scale Cost Est. ($/kg)"] = EMPTY_VALUE
    row["Bulk Cost Est. ($/kg)"] = EMPTY_VALUE
    row["NFPA Source"] = EMPTY_VALUE

    # --- On-demand TCI SDS (prefer over PubChem for NFPA + phys when present) ---
    if enable_tci:
        try:
            tci = enrich_from_tci(cas, fetch_pricing=True)
            if tci.get("sds_url") and tci.get("ok"):
                # Prefer TCI SDS link when we actually got a PDF / useful fields
                if tci.get("product_number"):
                    row["SDS Link"] = tci["sds_url"]
                    prop_sources["SDS Link"] = f"TCI ({tci['product_number']})"

            if tci.get("nfpa_health"):
                nfpa_health_cands.append((tci["nfpa_health"], "TCI SDS"))
            if tci.get("nfpa_flame"):
                nfpa_flame_cands.append((tci["nfpa_flame"], "TCI SDS"))

            for tci_key, col in PHYS_COLS.items():
                if tci.get(tci_key) is not None:
                    digits = 2 if "Vapor" in col or "Viscosity" in col else 1
                    row[col] = _fmt_num(tci[tci_key], digits)
                    prop_sources[col] = "TCI SDS"

            if tci.get("water_solubility_raw"):
                raw = str(tci["water_solubility_raw"]).lower()
                if "miscible" in raw:
                    row["Water Solubility (g/L)"] = "miscible"
                    prop_sources["Water Solubility (g/L)"] = "TCI SDS"
                elif "insoluble" in raw or "immiscible" in raw:
                    row["Water Solubility (g/L)"] = "insoluble"
                    prop_sources["Water Solubility (g/L)"] = "TCI SDS"

            if tci.get("lab_cost_per_g") is not None:
                per_kg = _cost_per_kg_from_per_g(tci["lab_cost_per_g"])
                if per_kg is not None:
                    row["Lab Scale Cost Est. ($/kg)"] = _fmt_num(per_kg, 2)
                    prop_sources["Lab Scale Cost Est. ($/kg)"] = "TCI product page"
                if tci.get("lab_cost_note"):
                    notes.append(f"TCI price: {tci['lab_cost_note']} (stored as $/kg)")

            # Gloves: never let TCI "Impervious gloves" overwrite curated or HSP.
            # Prefer curated map; else accept a specific SDS material only.
            gt = (tci.get("glove_type") or "").strip()
            gt_l = gt.lower()
            if gt and gt_l not in {"impervious gloves", "protective gloves", "unknown", "impervious"}:
                if not curated_glove:
                    row["Glove Type"] = gt
                    prop_sources["Glove Type"] = "TCI SDS"
                else:
                    notes.append(f"TCI gloves (kept curated): {gt}")
            elif tci.get("glove_raw") and not curated_glove:
                notes.append(f"TCI gloves: {tci['glove_raw']}")

            if tci.get("error") and not tci.get("ok"):
                notes.append(f"TCI: {tci['error']}")
            elif tci.get("product_number"):
                notes.append(f"TCI product {tci['product_number']}")
        except Exception as exc:
            notes.append(f"TCI enrich skipped: {exc}")


    # --- On-demand Fisher SDS (prefer over PubChem/TCI for NFPA + cost + SDS + §9 when present) ---
    if enable_fisher:
        try:
            fisher = enrich_from_fisher(cas, fetch_pricing=True)
            if fisher.get("sds_url") and (fisher.get("ok") or fisher.get("part_number")):
                if fisher.get("part_number") and (
                    fisher.get("nfpa_health")
                    or fisher.get("nfpa_flame")
                    or fisher.get("lab_cost_per_g") is not None
                    or fisher.get("ok")
                ):
                    row["SDS Link"] = fisher["sds_url"]
                    prop_sources["SDS Link"] = f"Fisher SDS ({fisher['part_number']})"

            if fisher.get("nfpa_health"):
                nfpa_health_cands.append((fisher["nfpa_health"], "Fisher SDS"))
            if fisher.get("nfpa_flame"):
                nfpa_flame_cands.append((fisher["nfpa_flame"], "Fisher SDS"))

            for fish_key, col in PHYS_COLS.items():
                if fisher.get(fish_key) is not None:
                    digits = 2 if "Vapor" in col or "Viscosity" in col else 1
                    row[col] = _fmt_num(fisher[fish_key], digits)
                    prop_sources[col] = "Fisher SDS"

            if fisher.get("lab_cost_per_g") is not None:
                per_kg = _cost_per_kg_from_per_g(fisher["lab_cost_per_g"])
                if per_kg is not None:
                    row["Lab Scale Cost Est. ($/kg)"] = _fmt_num(per_kg, 2)
                    prop_sources["Lab Scale Cost Est. ($/kg)"] = "Fisher product page"
                if fisher.get("lab_cost_note"):
                    notes.append(f"Fisher price: {fisher['lab_cost_note']} (stored as $/kg)")

            # Gloves: only specific named materials; never overwrite curated or generic.
            gt = (fisher.get("glove_type") or "").strip()
            gt_l = gt.lower()
            generic_gloves = {
                "impervious gloves",
                "protective gloves",
                "appropriate protective gloves",
                "unknown",
                "impervious",
            }
            if gt and gt_l not in generic_gloves:
                if not curated_glove:
                    row["Glove Type"] = gt
                    prop_sources["Glove Type"] = "Fisher SDS"
                else:
                    notes.append(f"Fisher gloves (kept curated): {gt}")
            elif fisher.get("glove_raw"):
                notes.append(f"Fisher gloves (generic, ignored): {fisher['glove_raw']}")

            if fisher.get("error") and not fisher.get("ok"):
                notes.append(f"Fisher: {fisher['error']}")
            elif fisher.get("part_number"):
                notes.append(f"Fisher part {fisher['part_number']}")
        except Exception as exc:
            notes.append(f"Fisher enrich skipped: {exc}")

    # --- Precautionary NFPA merge (higher rating wins; cite all sources on disagreement) ---
    h_val, h_note = _precautionary_nfpa(nfpa_health_cands)
    f_val, f_note = _precautionary_nfpa(nfpa_flame_cands)
    if h_val is not None:
        row["NFPA Health"] = h_val
        prop_sources["NFPA Health"] = h_note
    if f_val is not None:
        row["NFPA Flame"] = f_val
        prop_sources["NFPA Flame"] = f_note
    if h_note or f_note:
        src_bits = []
        if h_note:
            src_bits.append(f"H:{h_note}")
        if f_note:
            src_bits.append(f"F:{f_note}")
        row["NFPA Source"] = " | ".join(src_bits)
        if "precautionary" in (h_note or "") or "precautionary" in (f_note or ""):
            notes.append(f"NFPA precautionary: {row['NFPA Source']}")

    # Sigma stub — does not invent prices; Millipore access pending
    if row["Lab Scale Cost Est. ($/kg)"] == EMPTY_VALUE:
        _ = enrich_from_sigma(cas)  # documents pending hook; no network call

    # --- HSP glove incompatibility flag (secondary to curated / specific SDS) ---
    glove_flag = format_glove_hsp_flag(
        solvent_d=solvent_d,
        solvent_p=solvent_p,
        solvent_h=solvent_h,
        known_glove=row.get("Glove Type"),
    )
    if glove_flag:
        prev = (row.get("Glove Type") or "").strip()
        prev_src = prop_sources.get("Glove Type", "")
        row["Glove Type"] = glove_flag
        if prev and prev.lower() not in {"unknown", "-", "impervious gloves", "protective gloves"} and not prev.startswith("needs_"):
            if glove_flag != prev:
                prop_sources["Glove Type"] = (
                    f"{prev_src} + HSP note" if prev_src else "curated/SDS + HSP note"
                )
        else:
            prop_sources["Glove Type"] = "HSPiP polymer screen"

    # Molar volume from MW + density
    mw_val = pubchem_data.get("molecular_weight")
    density_str = row.get("Density (g/L)", EMPTY_VALUE)
    if mw_val and density_str not in [EMPTY_VALUE, ""]:
        try:
            mw_float = float(mw_val)
            d_float = float(density_str)
            if d_float > 0:
                molar_vol = (mw_float / d_float) * 1000
                row["Molar Volume"] = _fmt_num(molar_vol, 1)
                prop_sources["Molar Volume"] = "calculated"
        except (ValueError, TypeError):
            pass

    # --- P2OASys (expert CSV → SQLite expert → SQLite auto) ---
    p2 = resolve_p2oasys(cas, expert_df)
    row["P2OASys"] = p2["overall"]
    row["P2OASys Source"] = p2["source"]
    if p2["source"] != EMPTY_VALUE:
        prop_sources["P2OASys"] = f"{p2['source']} ({p2.get('detail', '')})"


    # --- Optional ECOSAR (PyEPISuite remote) — notes only; never auto-fill P2OASys Ecological ---
    if enable_ecosar:
        try:
            eco = summarize_ecosar_for_cas(cas)
            if eco.get("ok"):
                note = eco.get("note") or "ok (no acute summary fields)"
                notes.append(f"ECOSAR: {note}")
            else:
                err = eco.get("error") or "unknown_error"
                notes.append(f"ECOSAR: {err}")
        except Exception as exc:
            notes.append(f"ECOSAR: {type(exc).__name__}: {exc}")

    row["_prop_sources"] = prop_sources
    row["_enrich_notes"] = notes
    return row


def generate_csv(rows: List[Dict[str, Any]]) -> str:
    """Generate CSV string from list of DoSS rows."""
    formatted_rows = [format_row_for_csv(r) for r in rows]
    df = pd.DataFrame(formatted_rows, columns=DOSS_COLUMNS)
    return df.to_csv(index=False)


def render_coverage_sidebar(row: Dict[str, Any]):
    """Render coverage checklist in sidebar with source notes."""
    st.sidebar.markdown("### Column Coverage")

    report = coverage_report(row)
    filled_count = sum(report.values())
    total_count = len(report)

    st.sidebar.progress(filled_count / total_count)
    st.sidebar.markdown(f"**{filled_count}/{total_count}** columns filled")

    st.sidebar.markdown("---")

    prop_sources: Dict[str, str] = row.get("_prop_sources") or {}
    filled_cols = []
    empty_cols = []
    placeholder_cols = []

    for col, is_filled in report.items():
        value = row.get(col, EMPTY_VALUE)
        if value == HSP_PLACEHOLDER:
            placeholder_cols.append(col)
        elif is_filled:
            filled_cols.append(col)
        else:
            empty_cols.append(col)

    # HSP D/P/H/RER listed under HSPiP section below; omit from generic filled list
    filled_other = [
        c for c in filled_cols
        if not (
            c in ("D", "P", "H", "RER (HSP)")
            and str(prop_sources.get(c, "")).startswith("HSPiP")
        )
    ]

    if filled_other:
        st.sidebar.markdown("**Filled (with source):**")
        for col in filled_other:
            src = prop_sources.get(col, "")
            suffix = f" — *{src}*" if src else ""
            st.sidebar.markdown(f"✅ {col}{suffix}")

    hsp_filled = [
        c for c in filled_cols
        if c in ("D", "P", "H", "RER (HSP)")
        and str(prop_sources.get(c, "")).startswith("HSPiP")
    ]
    pubchem_filled = [
        c for c in filled_cols
        if "PubChem" in str(prop_sources.get(c, ""))
    ]

    if hsp_filled:
        st.sidebar.markdown("**HSPiP (local sofx):**")
        for col in hsp_filled:
            src = prop_sources.get(col, "")
            st.sidebar.markdown(f"✅ {col} — *{src}*")

    if placeholder_cols:
        st.sidebar.markdown("**Needs HSPiP:**")
        for col in placeholder_cols:
            st.sidebar.markdown(f"🔶 {col}")
        st.sidebar.caption("Provide HSPiP.exe above to compute new CAS via CLI")
        exe_info = resolve_hspip_exe(st.session_state.get("hspip_exe_raw") or "")
        if exe_info.get("ok"):
            if st.sidebar.button("Compute HSP via CLI", key="cli_hsp_btn"):
                result = run_cli_for_row(row, exe_info)
                if result.get("ok"):
                    apply_cli_hsp_to_row(row, result)
                    st.session_state["current_row"] = row
                    st.session_state["current_rows"] = [row]
                    st.sidebar.success(result.get("source_label") or "CLI filled D/P/H")
                    st.rerun()
                else:
                    st.sidebar.error(result.get("error") or "CLI failed; D/P/H not invented")
        else:
            st.sidebar.caption("Set HSPiP.exe in **HSPiP setup** to enable the CLI button.")

    st.sidebar.caption(
        f"Sources: HSPiP={len(hsp_filled)} · needs_HSPiP={len(placeholder_cols)} · "
        f"PubChem-tagged={len(pubchem_filled)}"
    )

    if empty_cols:
        st.sidebar.markdown("**Not available:**")
        for col in empty_cols:
            st.sidebar.markdown(f"❌ {col}")

    notes = row.get("_enrich_notes") or []
    if notes:
        st.sidebar.markdown("---")
        st.sidebar.markdown("**Enrichment notes:**")
        for n in notes:
            st.sidebar.caption(n)

    glove = str(row.get("Glove Type", ""))
    if "incompatible" in glove.lower() or "HSP" in glove or "should not dissolve" in glove.lower():
        st.sidebar.markdown("---")
        st.sidebar.info(
            "Glove HSP flags are **HSP-predicted** (not breakthrough time). "
            "Polymer spheres from published glove-material Hansen fits "
            "(pchem4all / DefaultPolymers-style Ro)."
        )


def main():
    st.title("🧪 TURI Safe Chem DB")
    st.markdown(
        "Enter a CAS number (example: acetone `67-64-1`). "
        "We'll build a safer-solvent (DoSS) row."
    )

    expert_df = load_expert_csv()

    st.sidebar.markdown("## Settings")

    uploaded_file = st.sidebar.file_uploader(
        "Upload P2OASys Expert CSV",
        type=["csv"],
        help="CSV with 'cas' column and Auto6 category max columns for P2OASys scoring",
    )
    if uploaded_file is not None:
        try:
            expert_df = pd.read_csv(uploaded_file)
            cols_lower = {c.lower(): c for c in expert_df.columns}
            if "cas" in cols_lower and cols_lower["cas"] != "cas":
                expert_df = expert_df.rename(columns={cols_lower["cas"]: "cas"})
            expert_df["cas"] = expert_df["cas"].astype(str).str.strip()
            st.sidebar.success("Loaded P2OASys expert data (upload)")
        except Exception as e:
            st.sidebar.error(f"Failed to load CSV: {e}")
    elif expert_df is not None:
        src = (
            os.environ.get("EXPERT_P2OASYS_CSV")
            if os.environ.get("EXPERT_P2OASYS_CSV")
            and os.path.exists(os.environ.get("EXPERT_P2OASYS_CSV", ""))
            else str(DEFAULT_EXPERT_CSV)
        )
        st.sidebar.info(f"Expert CSV: `{os.path.basename(src)}` ({len(expert_df)} rows)")
    else:
        st.sidebar.warning("No expert P2OASys CSV loaded")

    _lookup_db = default_lookup_db_path()
    if _lookup_db.is_file():
        st.sidebar.caption(f"Auto/expert SQLite: `{_lookup_db.name}`")
    else:
        st.sidebar.caption("P2OASys score lookup DB not found (auto fallback unavailable)")

    # Vendor toggles under expander — keep defaults ON for enrichment
    _fisher_env = (os.environ.get("DOSS_ENABLE_FISHER") or "1").strip().lower()
    _fisher_default = _fisher_env not in ("0", "false", "no", "off")
    with st.sidebar.expander("Advanced / data sources", expanded=False):
        st.caption("Optional vendor SDS lookups (need network). Leave on for fuller rows.")
        enable_tci = st.checkbox(
            "On-demand TCI SDS enrich",
            value=True,
            help="Fetch TCI SDS for NFPA / physchem / pricing when catalog has a product code. Not a mass scrape.",
        )
        enable_fisher = st.checkbox(
            "Fisher SDS enrich",
            value=_fisher_default,
            help="Fetch Fisher Scientific SDS / product page for NFPA, lab $/kg, SDS link, and §9 physchem when catalog has a part number. Prefer Fisher over PubChem/TCI when filled. Not a mass scrape. Default from DOSS_ENABLE_FISHER (1/0).",
        )
        _ecosar_env = (os.environ.get("DOSS_ENABLE_ECOSAR") or "0").strip().lower()
        _ecosar_default = _ecosar_env in ("1", "true", "yes", "on")
        enable_ecosar = st.checkbox(
            "ECOSAR (PyEPISuite remote API)",
            value=_ecosar_default,
            help=(
                "Optional aquatic QSAR via unofficial pyepisuite remote API (not EPA; needs network). "
                "Appends enrichment notes only — does NOT invent values and does NOT auto-fill "
                "P2OASys Ecological subcategory scores. Default from DOSS_ENABLE_ECOSAR (0/1)."
            ),
            disabled=not ecosar_available(),
        )
        if not ecosar_available():
            st.caption("ECOSAR unavailable — install optional `requirements-ecosar.txt` (pyepisuite).")

    hsp_setup = render_hspip_setup_sidebar()

    st.sidebar.markdown("---")

    tab1, tab2 = st.tabs(["Single Lookup", "Batch Mode"])

    with tab1:
        col1, col2 = st.columns([1, 2])

        with col1:
            cas_input = st.text_input(
                "CAS Number",
                placeholder="e.g., 67-64-1 (acetone)",
                help="Chemical ID — try acetone 67-64-1",
            )
            name_input = st.text_input(
                "Solvent Name (optional)",
                placeholder="e.g., Acetone",
                help="Override the name from PubChem",
            )
            generate_btn = st.button("Generate Row", type="primary", use_container_width=True)

        if generate_btn and cas_input:
            with st.spinner("Fetching PubChem / P2OASys / Fisher / TCI / optional ECOSAR…"):
                try:
                    pubchem_data = fetch_compound_data(
                        cas_input.strip(),
                        name_hint=name_input.strip() if name_input else None,
                    )
                    row = build_doss_row(
                        pubchem_data,
                        expert_df,
                        enable_tci=enable_tci,
                        enable_fisher=enable_fisher,
                        enable_ecosar=enable_ecosar,
                    )
                    smiles = pubchem_data.get("smiles") or ""
                    if smiles:
                        row["_smiles"] = smiles
                        st.session_state["current_smiles"] = smiles
                    if (
                        hsp_setup.get("auto_cli")
                        and row.get("D") == HSP_PLACEHOLDER
                        and hsp_setup.get("exe_info", {}).get("ok")
                    ):
                        result = run_cli_for_row(row, hsp_setup["exe_info"])
                        row = apply_cli_hsp_to_row(row, result)
                    st.session_state["current_row"] = row
                    st.session_state["current_rows"] = [row]
                except PubChemError as e:
                    st.error(f"PubChem lookup failed: {e}")
                except Exception as e:
                    st.error(f"Error generating row: {e}")

        if "current_row" in st.session_state:
            row = st.session_state["current_row"]

            st.markdown("### Generated DoSS Row")
            src = row.get("P2OASys Source", EMPTY_VALUE)
            st.caption(
                f"P2OASys={row.get('P2OASys', EMPTY_VALUE)} "
                f"(source={src}) · NFPA H/F={row.get('NFPA Health')}/{row.get('NFPA Flame')} · "
                f"Lab $/kg={row.get('Lab Scale Cost Est. ($/kg)')}"
            )

            df = pd.DataFrame([format_row_for_csv(row)], columns=DOSS_COLUMNS)
            st.dataframe(df, use_container_width=True)

            csv_data = generate_csv([row])
            cas_clean = row.get("CAS", "compound").replace("-", "")
            filename = f"doss_{cas_clean}.csv"

            st.download_button(
                label="📥 Download CSV",
                data=csv_data,
                file_name=filename,
                mime="text/csv",
                use_container_width=True,
            )

            render_coverage_sidebar(row)

    with tab2:
        st.markdown("Paste multiple CAS numbers (one per line) for batch processing.")

        batch_input = st.text_area(
            "CAS Numbers (one per line)",
            height=150,
            placeholder="67-64-1\n64-17-5\n67-56-1",
        )

        batch_btn = st.button("Generate Batch", type="primary", key="batch_btn")

        if batch_btn and batch_input:
            cas_list = [
                line.strip()
                for line in batch_input.strip().split("\n")
                if line.strip()
            ]

            if not cas_list:
                st.warning("No valid CAS numbers found")
            else:
                progress_bar = st.progress(0)
                status_text = st.empty()

                rows = []
                errors = []

                for i, cas in enumerate(cas_list):
                    status_text.text(f"Processing {cas} ({i+1}/{len(cas_list)})")
                    progress_bar.progress((i + 1) / len(cas_list))

                    try:
                        pubchem_data = fetch_compound_data(cas)
                        row = build_doss_row(
                            pubchem_data,
                            expert_df,
                            enable_tci=enable_tci,
                            enable_fisher=enable_fisher,
                            enable_ecosar=enable_ecosar,
                        )
                        rows.append(row)
                    except Exception as e:
                        errors.append(f"{cas}: {e}")
                        empty = empty_row()
                        empty["CAS"] = cas
                        empty["P2OASys Source"] = EMPTY_VALUE
                        rows.append(empty)

                status_text.text("Done!")

                if errors:
                    with st.expander(f"⚠️ {len(errors)} lookup errors"):
                        for err in errors:
                            st.text(err)

                if rows:
                    st.markdown(f"### Generated {len(rows)} DoSS Rows")

                    df = pd.DataFrame(
                        [format_row_for_csv(r) for r in rows],
                        columns=DOSS_COLUMNS,
                    )
                    st.dataframe(df, use_container_width=True)

                    csv_data = generate_csv(rows)

                    st.download_button(
                        label="📥 Download Batch CSV",
                        data=csv_data,
                        file_name="doss_batch.csv",
                        mime="text/csv",
                        use_container_width=True,
                    )

    paths = documented_paths()
    st.markdown("---")
    st.markdown(
        f"""
        <small>
        <b>Data Sources:</b> PubChem PUG REST; expert P2OASys CSV
        (<code>{os.path.basename(paths['default_expert_csv'])}</code> /
        <code>EXPERT_P2OASYS_CSV</code>); bundled harvest/auto lookup
        <code>data/p2oasys_score_lookup.sqlite</code> (override
        <code>P2OASYS_SCORE_LOOKUP_DB</code>); on-demand <b>Fisher</b> and <b>TCI</b> SDS/catalog
        (best-effort; TCI may hit Akamai/403 — local cache used when present).
        Optional <b>ECOSAR</b> via <code>pyepisuite</code> remote API (unofficial; not EPA; no EPA binary redistributed; notes only — does not auto-fill P2OASys Ecological). Sigma/Millipore stubbed (access pending).<br>
        <b>P2OASys:</b> expert overall = site evaluation when available, else mean of
        Auto6 category maxima; auto = max of Auto6; source column =
        <code>expert</code> | <code>auto</code> | <code>-</code>.<br>
        <b>Reference:</b> Column structure matches TURI DoSS.xlsx sheet
        'DoSS original datapoints'.<br>
        <b>Note:</b> D/P/H/RER filled from local HSPiP <code>.sofx</code> when CAS hits;
        otherwise <code>needs_HSPiP</code>. Glove HSP flags are predicted (not breakthrough time).
        Never invent scores, prices, or HSP values.
        </small>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
