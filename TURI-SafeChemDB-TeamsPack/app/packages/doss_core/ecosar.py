"""ECOSAR via unofficial PyEPISuite remote API (no EPA binary redistributed).

Uses network EPI Suite API through pyepisuite (MIT, unaffiliated with EPA).
Set PYEPISUITE_MODE=remote for API-only. Never invents values.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

os.environ.setdefault("PYEPISUITE_MODE", "remote")


def _norm_cas(cas: str) -> str:
    return (cas or "").strip()


def ecosar_available() -> bool:
    try:
        import pyepisuite  # noqa: F401

        return True
    except ImportError:
        return False


def fetch_ecosar_rows(cas_list: List[str]) -> Dict[str, Any]:
    """Batch fetch ECOSAR rows for CAS list."""
    out: Dict[str, Any] = {
        "ok": False,
        "error": None,
        "n_cas": len(cas_list),
        "n_rows": 0,
        "columns": [],
        "records": [],
    }
    if not cas_list:
        out["error"] = "empty_cas_list"
        return out
    if not ecosar_available():
        out["error"] = "pyepisuite_not_installed"
        return out
    try:
        from pyepisuite import search_episuite_by_cas, submit_to_episuite
        from pyepisuite.dataframe_utils import ecosar_to_dataframe

        ids = search_episuite_by_cas([_norm_cas(c) for c in cas_list])
        _epi, ecosar_results = submit_to_episuite(ids)
        df = ecosar_to_dataframe(ecosar_results)
        out["ok"] = True
        out["n_rows"] = int(len(df))
        out["columns"] = list(df.columns)
        out["records"] = df.to_dict(orient="records")
        return out
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
        return out


def summarize_ecosar_for_cas(
    cas: str, records: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """Compact acute summary for one CAS (fish/daphnid/algae)."""
    cas_n = _norm_cas(cas)
    summary: Dict[str, Any] = {
        "cas": cas_n,
        "ok": False,
        "qsar_class": None,
        "fish_96h_lc50": None,
        "daphnid_48h_lc50": None,
        "algae_96h_ec50": None,
        "n_rows": 0,
        "note": None,
        "error": None,
    }
    if records is None:
        batch = fetch_ecosar_rows([cas_n])
        if not batch.get("ok"):
            summary["error"] = batch.get("error")
            return summary
        records = batch.get("records") or []

    def _cas_match(row_cas: str) -> bool:
        a = str(row_cas or "").lstrip("0") or "0"
        b = cas_n.lstrip("0") or "0"
        return a == b or str(row_cas) == cas_n

    rows = [r for r in records if _cas_match(str(r.get("cas", "")))]
    summary["n_rows"] = len(rows)
    if not rows:
        summary["error"] = "no_ecosar_rows"
        return summary

    summary["ok"] = True
    summary["qsar_class"] = rows[0].get("qsar_class")

    def _pick(organism: str, endpoint: str, duration_substr: str):
        for r in rows:
            org = str(r.get("organism") or "")
            ep = str(r.get("endpoint") or "")
            dur = str(r.get("duration") or "")
            if "SW" in org and organism.lower() == "fish":
                continue
            if (
                organism.lower() in org.lower()
                and ep == endpoint
                and duration_substr in dur
            ):
                return r.get("concentration")
        return None

    summary["fish_96h_lc50"] = _pick("Fish", "LC50", "96")
    summary["daphnid_48h_lc50"] = _pick("Daphnid", "LC50", "48")
    summary["algae_96h_ec50"] = _pick("Algae", "EC50", "96")
    bits = []
    if summary["qsar_class"]:
        bits.append(str(summary["qsar_class"]))
    if summary["fish_96h_lc50"] is not None:
        bits.append(f"Fish 96h LC50={summary['fish_96h_lc50']}")
    if summary["daphnid_48h_lc50"] is not None:
        bits.append(f"Daphnid 48h LC50={summary['daphnid_48h_lc50']}")
    if summary["algae_96h_ec50"] is not None:
        bits.append(f"Algae 96h EC50={summary['algae_96h_ec50']}")
    summary["note"] = "; ".join(bits) if bits else None
    return summary
