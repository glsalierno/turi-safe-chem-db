"""Batch DoSS report for the priority solvent CAS list (data/priority_cas_list.txt).

Usage (from doss-ondemand folder, or any cwd):
  set EXPERT_P2OASYS_CSV=...\\priority_expert_p2oasys_scores.csv
  python scripts/batch_priority_doss.py

Writes into the app folder:
  priority62_doss_report.csv
  priority62_doss_report_summary.json
"""

from __future__ import annotations

import csv
import json
import os
import sys
import time
import types
from pathlib import Path
from typing import Any, Dict, List, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
APP_DIR = REPO_ROOT / "apps" / "doss_ondemand"
DATA_DIR = REPO_ROOT / "data"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Streamlit is imported at module level in app.py; stub it for CLI use.
if "streamlit" not in sys.modules:
    _st = types.ModuleType("streamlit")

    class _NoOp:
        def __call__(self, *a, **k):
            return None

        def __getattr__(self, name):
            return _NoOp()

    def _noop(*a, **k):
        return None

    def _checkbox(label, value=False, **k):
        return value

    _st.set_page_config = _noop
    _st.markdown = _noop
    _st.title = _noop
    _st.caption = _noop
    _st.info = _noop
    _st.warning = _noop
    _st.error = _noop
    _st.success = _noop
    _st.sidebar = _NoOp()
    _st.checkbox = _checkbox
    _st.text_input = lambda *a, **k: ""
    _st.text_area = lambda *a, **k: ""
    _st.button = lambda *a, **k: False
    _st.file_uploader = lambda *a, **k: None
    _st.tabs = lambda *a, **k: (_NoOp(), _NoOp())
    _st.columns = lambda *a, **k: (_NoOp(), _NoOp())
    _st.progress = lambda *a, **k: _NoOp()
    _st.empty = lambda *a, **k: _NoOp()
    _st.spinner = lambda *a, **k: _NoOp()
    _st.dataframe = _noop
    _st.download_button = _noop
    _st.expander = lambda *a, **k: _NoOp()
    _st.session_state = {}
    sys.modules["streamlit"] = _st

from packages.doss_core.schema import (  # noqa: E402
    DOSS_COLUMNS,
    EMPTY_VALUE,
    HSP_PLACEHOLDER,
    empty_row,
)
from packages.p2oasys_core.lookup import load_expert_csv, resolve_p2oasys  # noqa: E402
from packages.doss_core.pubchem import PubChemError, fetch_compound_data  # noqa: E402
from apps.doss_ondemand.app import build_doss_row, generate_csv  # noqa: E402

CAS_LIST_PATH = APP_DIR / "priority_cas_list.txt"
QUEUE_PATH = APP_DIR / "priority_solvents_queue.csv"
EXPERT_CSV = APP_DIR / "priority_expert_p2oasys_scores.csv"
OUT_CSV = APP_DIR / "priority62_doss_report.csv"
OUT_SUMMARY = APP_DIR / "priority62_doss_report_summary.json"

SLEEP_BETWEEN_S = 0.4


def load_cas_list(path: Path) -> List[str]:
    cas_list: List[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        cas = line.strip()
        if cas and not cas.startswith("#"):
            cas_list.append(cas)
    return cas_list


def load_name_map(path: Path) -> Dict[str, str]:
    names: Dict[str, str] = {}
    if not path.is_file():
        return names
    with path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            cas = (row.get("cas") or "").strip()
            name = (row.get("name") or "").strip()
            if cas and name:
                names[cas] = name
    return names


def error_row(
    cas: str,
    name_hint: Optional[str],
    err: str,
    expert_df=None,
) -> Dict[str, Any]:
    """Emit a DoSS-shaped row on failure; still attach P2OASys when expert/auto available."""
    row = empty_row()
    row["CAS"] = cas
    if name_hint:
        row["Solvent Name"] = name_hint
    row["D"] = HSP_PLACEHOLDER
    row["P"] = HSP_PLACEHOLDER
    row["H"] = HSP_PLACEHOLDER
    row["RER (HSP)"] = HSP_PLACEHOLDER
    p2 = resolve_p2oasys(cas, expert_df)
    row["P2OASys"] = p2["overall"]
    row["P2OASys Source"] = p2["source"]
    row["_prop_sources"] = {}
    if p2["source"] != EMPTY_VALUE:
        row["_prop_sources"]["P2OASys"] = f"{p2['source']} ({p2.get('detail', '')})"
    row["_enrich_notes"] = [f"batch_error: {err}"]
    row["_batch_error"] = err
    return row


def _is_filled(val: Any) -> bool:
    return val is not None and str(val).strip() not in ("", EMPTY_VALUE, HSP_PLACEHOLDER)


def summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(rows)
    ok = 0
    pubchem_fail = 0
    p2_expert = 0
    p2_auto = 0
    p2_blank = 0
    nfpa_filled = 0
    glove_filled = 0
    tci_used = 0
    fisher_used = 0
    cost_filled = 0
    nfpa_precautionary = 0
    needs_hspip = 0

    for r in rows:
        notes = r.get("_enrich_notes") or []
        sources = r.get("_prop_sources") or {}

        if r.get("_batch_error") or any(str(n).startswith("batch_error:") for n in notes):
            pubchem_fail += 1
        else:
            ok += 1

        src = str(r.get("P2OASys Source", EMPTY_VALUE)).strip().lower()
        if src == "expert":
            p2_expert += 1
        elif src == "auto":
            p2_auto += 1
        else:
            p2_blank += 1

        if _is_filled(r.get("NFPA Health")) or _is_filled(r.get("NFPA Flame")):
            nfpa_filled += 1

        glove = str(r.get("Glove Type", "Unknown")).strip()
        if glove and glove.lower() not in ("unknown", EMPTY_VALUE, "-"):
            glove_filled += 1

        if any(isinstance(v, str) and ("TCI" in v) for v in sources.values()):
            tci_used += 1

        if any(isinstance(v, str) and ("Fisher" in v) for v in sources.values()):
            fisher_used += 1

        if _is_filled(r.get("Lab Scale Cost Est. ($/kg)")) or _is_filled(r.get("Bulk Cost Est. ($/kg)")):
            cost_filled += 1

        nfpa_src = str(r.get("NFPA Source", "") or "")
        if "precautionary" in nfpa_src.lower() or any(
            isinstance(n, str) and "precautionary" in n.lower() for n in notes
        ):
            nfpa_precautionary += 1

        if (
            r.get("D") == HSP_PLACEHOLDER
            and r.get("P") == HSP_PLACEHOLDER
            and r.get("H") == HSP_PLACEHOLDER
        ):
            needs_hspip += 1

    return {
        "total": total,
        "ok": ok,
        "pubchem_fail": pubchem_fail,
        "p2oasys_expert": p2_expert,
        "p2oasys_auto": p2_auto,
        "p2oasys_blank": p2_blank,
        "nfpa_filled": nfpa_filled,
        "glove_filled": glove_filled,
        "tci_used": tci_used,
        "fisher_used": fisher_used,
        "cost_filled_per_kg": cost_filled,
        "nfpa_precautionary": nfpa_precautionary,
        "needs_HSPiP_for_DPH": needs_hspip,
        "output_csv": str(OUT_CSV),
        "output_summary": str(OUT_SUMMARY),
    }


def main() -> int:
    os.environ.setdefault("EXPERT_P2OASYS_CSV", str(EXPERT_CSV))
    expert_path = Path(os.environ["EXPERT_P2OASYS_CSV"])
    if not expert_path.is_file():
        print(f"ERROR: expert CSV not found: {expert_path}", file=sys.stderr)
        return 1

    cas_list = load_cas_list(CAS_LIST_PATH)
    name_map = load_name_map(QUEUE_PATH)
    expert_df = load_expert_csv(expert_path)

    print(f"APP_DIR={APP_DIR}")
    print(f"EXPERT_P2OASYS_CSV={expert_path} (rows={0 if expert_df is None else len(expert_df)})")
    print(f"CAS count={len(cas_list)}")
    print(f"enable_tci=True enable_fisher=True  sleep={SLEEP_BETWEEN_S}s")

    rows: List[Dict[str, Any]] = []
    for i, cas in enumerate(cas_list, start=1):
        name_hint = name_map.get(cas)
        print(f"[{i}/{len(cas_list)}] {cas} {name_hint or ''}".rstrip(), flush=True)
        try:
            pubchem_data = fetch_compound_data(cas, name_hint=name_hint)
            if name_hint:
                pubchem_data["name"] = name_hint
            row = build_doss_row(
                pubchem_data, expert_df, enable_tci=True, enable_fisher=True
            )
            if pubchem_data.get("view_warning"):
                notes = row.setdefault("_enrich_notes", [])
                notes.append(f"pubchem_view_warning: {pubchem_data['view_warning']}")
            rows.append(row)
            print(
                f"  ok name={row.get('Solvent Name')} "
                f"P2={row.get('P2OASys')}/{row.get('P2OASys Source')} "
                f"NFPA={row.get('NFPA Health')}/{row.get('NFPA Flame')} "
                f"cost={row.get('Lab Scale Cost Est. ($/kg)')}/kg "
                f"glove={row.get('Glove Type')}",
                flush=True,
            )
        except PubChemError as e:
            print(f"  PubChem fail: {e}", flush=True)
            rows.append(error_row(cas, name_hint, f"PubChemError: {e}", expert_df))
        except Exception as e:
            print(f"  error: {e}", flush=True)
            rows.append(error_row(cas, name_hint, f"{type(e).__name__}: {e}", expert_df))

        if i < len(cas_list):
            time.sleep(SLEEP_BETWEEN_S)

    csv_text = generate_csv(rows)
    OUT_CSV.write_text(csv_text, encoding="utf-8")

    summary = summarize(rows)
    acetone = next((r for r in rows if r.get("CAS") == "67-64-1"), None)
    summary["acetone_check"] = None
    if acetone:
        summary["acetone_check"] = {
            "CAS": acetone.get("CAS"),
            "Solvent Name": acetone.get("Solvent Name"),
            "P2OASys": acetone.get("P2OASys"),
            "P2OASys Source": acetone.get("P2OASys Source"),
            "NFPA Health": acetone.get("NFPA Health"),
            "NFPA Flame": acetone.get("NFPA Flame"),
            "NFPA Source": acetone.get("NFPA Source"),
            "Lab Scale Cost Est. ($/kg)": acetone.get("Lab Scale Cost Est. ($/kg)"),
            "D": acetone.get("D"),
            "P": acetone.get("P"),
            "H": acetone.get("H"),
            "Glove Type": acetone.get("Glove Type"),
            "notes": acetone.get("_enrich_notes") or [],
        }

    summary["columns"] = DOSS_COLUMNS
    summary["csv_row_count"] = len(rows)

    OUT_SUMMARY.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nWrote {OUT_CSV}")
    print(f"Wrote {OUT_SUMMARY}")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())