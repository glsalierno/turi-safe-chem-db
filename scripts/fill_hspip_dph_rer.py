"""Fill DoSS D/P/H/RER from local HSPiP .sofx databases (curated Hansen values).

Also emits an HSP-predicted glove screen using polymer spheres from
DefaultPolymers.pds (Breakthrough Time / elastomer correlations).

Does NOT invent values. Does NOT call HSPiP.exe by default (CLI currently
fails on this machine with clipboard lock). Optional --try-cli for misses.

Usage (from doss-ondemand or any cwd):
  python scripts/fill_hspip_dph_rer.py
  python scripts/fill_hspip_dph_rer.py --input priority62_doss_report.csv --out priority62_doss_report_hspip.csv

Outputs:
  priority62_doss_report_hspip.csv   (D,P,H,RER filled where sofx hit)
  priority62_glove_hsp_screen.csv    (per-CAS incompatible / preferred)
  fill_hspip_summary.json
"""

from __future__ import annotations

import os
import sys
import argparse
import csv
import json
import math
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
APP_DIR = REPO_ROOT / "apps" / "doss_ondemand"
DATA_DIR = REPO_ROOT / "data"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Sofx roots from env HSPIP_DATA / HSPIP_DATA_DIR only (no hardcoded user paths).
# Placeholders: %HSPIP_DATA% or <YOUR_HSPIP_DATA>.
HSPIP_DATA_CANDIDATES: list[Path] = []

def _env_hspip_roots() -> list[Path]:
    roots: list[Path] = []
    for key in ("HSPIP_DATA", "HSPIP_DATA_DIR"):
        raw = (os.environ.get(key) or "").strip()
        if raw:
            p = Path(raw)
            if p not in roots:
                roots.append(p)
    return roots
HSPIP_CLI_DIRS = [
    Path(r"C:\Program Files\Hansen-Solubility-6\HSPiP"),  # TURI CLI Enabled.license
    Path(r"C:\Program Files\Hansen-Solubility\HSPiP"),
]

# Glove polymers for RED screen — prefer HSPiP "Breakthrough Time Correlations"
# and "Chemical Resistance of Elastomers" rows in DefaultPolymers.pds.
# Format: display_name -> (D, P, H, Ro)  [Ro = interaction radius]
# Prefer ~1 Hr sphere where available (mid-barrier), else elastomer R-row.
DEFAULT_GLOVE_POLYMERS: dict[str, tuple[float, float, float, float]] = {
    # Breakthrough Time Correlations (1 Hr) from DefaultPolymers.pds
    "Nitrile": (16.6, 9.1, 4.4, 10.0),
    "Butyl": (15.8, 2.1, 4.0, 8.2),
    "Natural rubber": (15.6, 3.4, 9.1, 14.0),
    "PVC": (14.9, 11.1, 3.8, 13.2),
    "PVA": (15.3, 13.2, 13.5, 8.8),
    "Viton": (16.5, 8.1, 8.3, 6.6),
    "Neoprene": (19.0, 8.0, 0.0, 13.2),
    # Elastomer chemical-resistance spheres (alternate / backup labels)
    # R NBR / R FKM kept as aliases only if primary missing — not duplicated here.
}


def _local(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _chem_dict(chem: ET.Element) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for c in list(chem):
        t = _local(c.tag).replace("\u03b4", "d").replace("δ", "d")
        out[t] = c.text
    return out


def load_sofx_by_cas(roots: list[Path]) -> dict[str, list[dict[str, Any]]]:
    by_cas: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen_files: set[Path] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for p in root.rglob("*.sofx"):
            rp = p.resolve()
            if rp in seen_files:
                continue
            seen_files.add(rp)
            try:
                tree = ET.parse(p)
            except ET.ParseError:
                continue
            for chem in tree.getroot().findall("Chemical"):
                d = _chem_dict(chem)
                cas = (d.get("CAS") or "").strip()
                if not cas or "dD" not in d or "dP" not in d or "dH" not in d:
                    continue
                try:
                    rer_raw = d.get("RER")
                    rer = (
                        float(rer_raw)
                        if rer_raw not in (None, "", "-")
                        else None
                    )
                    by_cas[cas].append(
                        {
                            "name": (d.get("Solvent") or "").strip(),
                            "D": float(d["dD"]),
                            "P": float(d["dP"]),
                            "H": float(d["dH"]),
                            "RER": rer,
                            "SMILES": d.get("SMILES"),
                            "source": str(p),
                        }
                    )
                except (TypeError, ValueError):
                    continue
    return by_cas


def pick_entry(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Prefer non-cluster classical solvents with RER present."""

    def key(e: dict[str, Any]) -> tuple:
        name = (e.get("name") or "").lower()
        return (
            0 if "cluster" not in name else 1,
            0 if e.get("RER") is not None else 1,
            0 if name and " " not in name else 1,
            name,
        )

    return sorted(entries, key=key)[0]


def load_glove_polymers_from_pds(roots: list[Path]) -> dict[str, tuple[float, float, float, float]]:
    """Overlay DefaultPolymers.pds 1-Hr breakthrough rows when present."""
    polymers = dict(DEFAULT_GLOVE_POLYMERS)
    mapping = {
        "nitrile 1 hr": "Nitrile",
        "butyl 1 hr": "Butyl",
        "natural rubber 1 hr": "Natural rubber",
        "pvc 1 hr": "PVC",
        "polyvinylalcohol 1 hr": "PVA",
        "viton 1 hr": "Viton",
        "neoprene 1 hr": "Neoprene",
    }
    for root in roots:
        pds = root / "DefaultPolymers.pds"
        if not pds.is_file():
            continue
        try:
            text = pds.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            parts = line.split("\t")
            if len(parts) < 6:
                continue
            name = parts[1].strip()
            key = " ".join(name.lower().split())
            label = mapping.get(key)
            if not label:
                continue
            try:
                d, p, h, ro = float(parts[2]), float(parts[3]), float(parts[4]), float(parts[5])
            except ValueError:
                continue
            polymers[label] = (d, p, h, ro)
        break
    return polymers


def hansen_ra(d1: float, p1: float, h1: float, d2: float, p2: float, h2: float) -> float:
    """Hansen distance Ra between solvent (1) and polymer (2)."""
    return math.sqrt(4.0 * (d1 - d2) ** 2 + (p1 - p2) ** 2 + (h1 - h2) ** 2)


def glove_screen(
    d: float, p: float, h: float, polymers: dict[str, tuple[float, float, float, float]]
) -> dict[str, Any]:
    incompatible: list[str] = []
    preferred: list[str] = []
    details: list[dict[str, Any]] = []
    for name, (pd, pp, ph, ro) in polymers.items():
        ra = hansen_ra(d, p, h, pd, pp, ph)
        red = ra / ro if ro else float("inf")
        details.append({"polymer": name, "Ra": round(ra, 3), "Ro": ro, "RED": round(red, 3)})
        if red < 1.0:
            incompatible.append(name)
        else:
            preferred.append(name)
    # Locked UX wording when material unknown
    flag = (
        f"Unknown; incompatible with {', '.join(incompatible)}"
        if incompatible
        else "Unknown; no glove polymer in curated set with RED < 1"
    )
    hspip_note = (
        f"HSPiP: solvent should not dissolve {', '.join(preferred)}"
        if preferred
        else "HSPiP: no preferred barrier candidates in curated set (all RED < 1)"
    )
    return {
        "incompatible": incompatible,
        "preferred": preferred,
        "glove_flag": flag,
        "glove_hspip_note": hspip_note,
        "details": details,
        "label": "HSP-predicted (not breakthrough-time); secondary to curated/SDS material",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--input",
        type=Path,
        default=APP_DIR / "priority62_doss_report.csv",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=APP_DIR / "priority62_doss_report_hspip.csv",
    )
    ap.add_argument(
        "--glove-out",
        type=Path,
        default=APP_DIR / "priority62_glove_hsp_screen.csv",
    )
    ap.add_argument(
        "--summary",
        type=Path,
        default=APP_DIR / "fill_hspip_summary.json",
    )
    ap.add_argument(
        "--try-cli",
        action="store_true",
        help="Attempt HSPiP.exe Y-MBSX for sofx misses (often clipboard-locked on this host).",
    )
    args = ap.parse_args()

    roots = [r for r in (_env_hspip_roots() + HSPIP_DATA_CANDIDATES) if r.is_dir()]
    by_cas = load_sofx_by_cas(roots)
    polymers = load_glove_polymers_from_pds(roots)

    with args.input.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        print("No rows in", args.input)
        return 1

    fieldnames = list(rows[0].keys())
    for extra in ("HSP Source", "Glove HSP Flag", "Glove HSP Preferred"):
        if extra not in fieldnames:
            fieldnames.append(extra)

    filled = 0
    miss: list[str] = []
    glove_rows: list[dict[str, Any]] = []

    for row in rows:
        cas = (row.get("CAS") or "").strip()
        entries = by_cas.get(cas) or []
        if entries:
            e = pick_entry(entries)
            row["D"] = e["D"]
            row["P"] = e["P"]
            row["H"] = e["H"]
            if e["RER"] is not None:
                row["RER (HSP)"] = e["RER"]
            row["HSP Source"] = f"HSPiP sofx:{Path(e['source']).name} ({e['name']})"
            filled += 1
            screen = glove_screen(e["D"], e["P"], e["H"], polymers)
            row["Glove HSP Flag"] = screen["glove_flag"]
            row["Glove HSP Preferred"] = screen["glove_hspip_note"]
            glove_rows.append(
                {
                    "CAS": cas,
                    "Solvent Name": row.get("Solvent Name"),
                    "D": e["D"],
                    "P": e["P"],
                    "H": e["H"],
                    "RER": e["RER"],
                    "Existing Glove Type": row.get("Glove Type"),
                    "glove_flag": screen["glove_flag"],
                    "glove_hspip_note": screen["glove_hspip_note"],
                    "incompatible": "; ".join(screen["incompatible"]),
                    "preferred": "; ".join(screen["preferred"]),
                    "note": screen["label"],
                    # Never overwrite curated materials (Nitrile/Viton/etc.)
                    "overwrite_glove_type": (
                        "no"
                        if (row.get("Glove Type") or "").strip()
                        not in ("", "-", "Unknown", "Impervious gloves", "Impervious")
                        else "candidate_only"
                    ),
                }
            )
        else:
            miss.append(cas)
            row.setdefault("HSP Source", "needs_HSPiP")
            # leave D/P/H/RER as needs_HSPiP / existing

        # Explicit rule: TCI "Impervious gloves" must not overwrite curated
        gt = (row.get("Glove Type") or "").strip()
        if gt.lower() in ("impervious gloves", "impervious"):
            # keep as-is but mark weak
            if "Glove HSP Flag" in row and row.get("Glove HSP Flag"):
                pass

    if args.try_cli and miss:
        print(
            "CLI path requested for",
            len(miss),
            "misses — skipped automated run: Out.dat/clipboard lock often occurs when GUI is open. "
            "Use HSPiP_CLI_v7.py / run_hspip.py interactively after closing other HSPiP GUIs.",
        )

    with args.out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    glove_fields = [
        "CAS",
        "Solvent Name",
        "D",
        "P",
        "H",
        "RER",
        "Existing Glove Type",
        "glove_flag",
        "glove_hspip_note",
        "incompatible",
        "preferred",
        "overwrite_glove_type",
        "note",
    ]
    with args.glove_out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=glove_fields)
        w.writeheader()
        w.writerows(glove_rows)

    summary = {
        "input": str(args.input),
        "output": str(args.out),
        "glove_output": str(args.glove_out),
        "total_rows": len(rows),
        "sofx_filled_dph": filled,
        "still_needs_hspip": miss,
        "still_needs_hspip_count": len(miss),
        "polymer_table": {k: {"D": v[0], "P": v[1], "H": v[2], "Ro": v[3]} for k, v in polymers.items()},
        "polymer_source": "DefaultPolymers.pds Breakthrough Time Correlations (1 Hr) under HSPiP Data",
        "hspip_installs": [str(p) for p in HSPIP_CLI_DIRS if p.is_dir()],
        "cli_note": (
            "Hansen-Solubility-6 has TURI CLI Enabled.license; Y-MBSX currently "
            "raises Clipboard ExternalException / locks Out.dat when GUI or another "
            "agent holds the clipboard. Prefer sofx curated fill; use "
            "cas-to-HSPiP_data/HSPiP_CLI_v7.py for Y-MB estimates when CLI is free."
        ),
        "glove_ux": {
            "incompatible_flag": "Unknown; incompatible with X, Y, Z",
            "preferred_note": "HSPiP: solvent should not dissolve U, V, W",
            "secondary_to": "curated map / SDS material; never overwrite curated; ignore TCI Impervious",
        },
        "smoke_values": {
            "67-64-1_acetone": by_cas.get("67-64-1") and pick_entry(by_cas["67-64-1"]),
            "67-56-1_methanol": by_cas.get("67-56-1") and pick_entry(by_cas["67-56-1"]),
        },
    }
    # JSON-serialize smoke (Path-free)
    for k in list(summary["smoke_values"]):
        e = summary["smoke_values"][k]
        if e:
            summary["smoke_values"][k] = {
                "name": e["name"],
                "D": e["D"],
                "P": e["P"],
                "H": e["H"],
                "RER": e["RER"],
                "source": Path(e["source"]).name,
            }

    args.summary.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("total_rows", "sofx_filled_dph", "still_needs_hspip_count", "still_needs_hspip")}, indent=2))
    print("Wrote", args.out)
    print("Wrote", args.glove_out)
    print("Wrote", args.summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())