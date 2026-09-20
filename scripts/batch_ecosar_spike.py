"""Run ECOSAR (PyEPISuite remote) on priority CAS; write CSV + summary JSON."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("PYEPISUITE_MODE", "remote")

from packages.doss_core.ecosar import fetch_ecosar_rows  # noqa: E402


def main() -> int:
    cas_path = ROOT / "data" / "priority_cas_list.txt"
    cas_list = [
        ln.strip()
        for ln in cas_path.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    cas_list = list(dict.fromkeys(cas_list))[:40]
    out_dir = ROOT / "data" / "ecosar_spike"
    out_dir.mkdir(parents=True, exist_ok=True)
    result = fetch_ecosar_rows(cas_list)
    (out_dir / "summary.json").write_text(
        json.dumps(
            {
                "ok": result.get("ok"),
                "error": result.get("error"),
                "n_cas": result.get("n_cas"),
                "n_rows": result.get("n_rows"),
                "columns": result.get("columns"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    if result.get("ok") and result.get("records"):
        import pandas as pd

        pd.DataFrame(result["records"]).to_csv(
            out_dir / "ecosar_spike_40.csv", index=False
        )
        print(f"PASS rows={result['n_rows']} -> {out_dir}")
        return 0
    print(f"FAIL {result.get('error')}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
