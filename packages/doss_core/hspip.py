"""
Local HSPiP sofx lookup: CAS -> D, P, H, RER, plus optional CLI hook.

Same source logic as scripts/fill_hspip_dph_rer.py. Never invents values;
returns None when CAS is absent from curated solvent tables.
CLI (HSPiP.exe Y-MBSX) is opt-in and only used when the user supplies a
licensed executable and a real SMILES.
"""

from __future__ import annotations

import csv
import os
import subprocess
import time
import xml.etree.ElementTree as ET
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any

# Sofx roots: env HSPIP_DATA/HSPIP_DATA_DIR, sidebar config, Teams sibling HSPiP_Data.
# Placeholders: %HSPIP_DATA%, <YOUR_HSPIP_DATA>. No hardcoded user-home / OneDrive paths.
HSPIP_DATA_CANDIDATES: list[Path] = []

REPO_ROOT = Path(__file__).resolve().parents[2]
REPO_CONFIG_PATH = REPO_ROOT / "config" / "hspip_path.txt"
USER_CONFIG_DIR = Path.home() / ".turi-safe-chem-db"
USER_CONFIG_PATH = USER_CONFIG_DIR / "hspip_path.txt"

OUT_DAT_COLUMNS = [
    "HSPiP_SMILES", "Formula", "D", "P", "H", "HDon", "HAcc", "MWt", "Density", "MVol",
    "Area", "Ovality", "BPt", "MPt", "Tc", "Pc", "Vc", "Zc", "AntA", "AntB",
    "AntC", "Ant1T", "LogKow", "LogS", "Henry", "LogOHR", "RI", "Hfus", "HvBPt",
    "Trouton", "RER", "Abra", "Abrb", "EdmiW", "Parachor", "RD", "Cp", "log",
    "Cond", "SurfTen", "HeavyAtom", "C", "H1", "Br", "Cl", "F", "I", "N", "O",
    "P1", "S", "Si", "B", "MaxPc", "MinMc", "Sym", "MCI", "Hcomb", "Hform",
    "Gform", "FGList",
]


def _env_hspip_roots() -> list[Path]:
    roots: list[Path] = []
    for key in ("HSPIP_DATA", "HSPIP_DATA_DIR"):
        raw = (os.environ.get(key) or "").strip()
        if not raw:
            continue
        p = Path(raw)
        if p not in roots:
            roots.append(p)
    return roots


def _teams_hspip_data() -> Path | None:
    """Teams pack layout: <pack>/app is repo root, sibling HSPiP_Data holds .sofx."""
    p = REPO_ROOT.parent / "HSPiP_Data"
    return p if p.is_dir() else None


def _teams_hspip_dir() -> Path | None:
    p = REPO_ROOT.parent / "HSPiP"
    return p if p.is_dir() else None


def _local(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _chem_dict(chem: ET.Element) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for c in list(chem):
        t = _local(c.tag).replace("\u03b4", "d").replace("δ", "d")
        out[t] = c.text
    return out


def resolve_hspip_roots(extra: list[Path] | None = None) -> list[Path]:
    """Resolve sofx library roots. Env HSPIP_DATA / HSPIP_DATA_DIR win over fallbacks."""
    roots: list[Path] = []
    teams = _teams_hspip_data()
    extras = list(extra or [])
    if teams is not None:
        extras.append(teams)
    for r in _env_hspip_roots() + extras + list(HSPIP_DATA_CANDIDATES):
        if r.is_dir() and r not in roots:
            roots.append(r)
    return roots


def load_sofx_by_cas(roots: list[Path] | None = None) -> dict[str, list[dict[str, Any]]]:
    """Index all *.sofx Chemical rows by CAS. Never invents numbers."""
    if roots is None:
        roots = resolve_hspip_roots()
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


@lru_cache(maxsize=1)
def _cached_index() -> dict[str, tuple[dict[str, Any], ...]]:
    raw = load_sofx_by_cas()
    return {cas: tuple(entries) for cas, entries in raw.items()}


def clear_cache() -> None:
    _cached_index.cache_clear()


def lookup_hspip(cas: str) -> dict[str, Any] | None:
    """
    Resolve CAS -> {D, P, H, RER, name, source, source_label}.

    Returns None if CAS is not in local sofx tables (caller keeps needs_HSPiP).
    Never invents values.
    """
    cas = (cas or "").strip()
    if not cas:
        return None
    entries = list(_cached_index().get(cas) or ())
    if not entries:
        # try alternate formatting (digits-only vs dashed) — still only real hits
        digits = "".join(c for c in cas if c.isdigit())
        if len(digits) >= 5:
            dashed = f"{digits[:-3]}-{digits[-3:-1]}-{digits[-1]}"
            entries = list(_cached_index().get(dashed) or ())
        if not entries and digits:
            for k, v in _cached_index().items():
                if "".join(c for c in k if c.isdigit()) == digits:
                    entries = list(v)
                    break
    if not entries:
        return None
    e = pick_entry(list(entries))
    src_name = Path(e["source"]).name
    return {
        "D": e["D"],
        "P": e["P"],
        "H": e["H"],
        "RER": e["RER"],
        "name": e["name"],
        "source": e["source"],
        "source_label": f"HSPiP sofx:{src_name}"
        + (f" ({e['name']})" if e.get("name") else ""),
    }


def format_hsp_number(val: float | None, digits: int = 1) -> str | None:
    if val is None:
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    # Prefer compact display matching fill script (15.5 not 15.50)
    if abs(f - round(f)) < 1e-9:
        return str(int(round(f))) if digits == 0 else str(round(f, digits))
    return str(round(f, digits))


def hspip_roots_status() -> dict[str, Any]:
    roots = resolve_hspip_roots()
    return {
        "roots": [str(r) for r in roots],
        "cas_count": len(_cached_index()) if roots else 0,
        "available": bool(roots),
    }


# ---------------------------------------------------------------------------
# Path persistence + HSPiP.exe validation + best-effort CLI (never invent)
# ---------------------------------------------------------------------------


def _read_config_file(path: Path) -> dict[str, str]:
    """Parse EXE=/DATA= keys or a bare first-line exe path."""
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    bare: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            key = k.strip().upper()
            val = v.strip().strip('"').strip("'")
            if key in {"EXE", "HSPIP_PATH", "HSPIP_EXE", "PATH"}:
                out["exe"] = val
            elif key in {"DATA", "HSPIP_DATA", "HSPIP_DATA_DIR"}:
                out["data"] = val
        else:
            bare.append(line.strip('"').strip("'"))
    if "exe" not in out and bare:
        out["exe"] = bare[0]
    if "data" not in out and len(bare) > 1:
        out["data"] = bare[1]
    return out


def load_saved_hspip_paths() -> dict[str, str]:
    """Repo-local config wins over ~/.turi-safe-chem-db/hspip_path.txt."""
    merged: dict[str, str] = {}
    for path in (USER_CONFIG_PATH, REPO_CONFIG_PATH):
        parsed = _read_config_file(path)
        merged.update({k: v for k, v in parsed.items() if v})
    return merged


def save_hspip_paths(exe_raw: str, data_raw: str = "") -> list[Path]:
    """Persist exe (+ optional data) to repo config and user app-data dir."""
    exe_raw = (exe_raw or "").strip()
    data_raw = (data_raw or "").strip()
    lines = ["# TURI Safe Chem DB - local HSPiP paths (do not commit)", f"EXE={exe_raw}"]
    if data_raw:
        lines.append(f"DATA={data_raw}")
    text = "\n".join(lines) + "\n"
    written: list[Path] = []
    for path in (REPO_CONFIG_PATH, USER_CONFIG_PATH):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            written.append(path)
        except OSError:
            continue
    return written


def default_hspip_exe_raw() -> str:
    """Env HSPIP_EXE / HSPIP_PATH, then saved config, then Teams HSPiP folder."""
    for key in ("HSPIP_EXE", "HSPIP_PATH"):
        raw = (os.environ.get(key) or "").strip()
        if raw:
            return raw
    saved = load_saved_hspip_paths().get("exe") or ""
    if saved:
        return saved
    teams = _teams_hspip_dir()
    return str(teams) if teams is not None else ""


def default_hspip_data_raw() -> str:
    """Env HSPIP_DATA / HSPIP_DATA_DIR, then saved config, then Teams HSPiP_Data."""
    for key in ("HSPIP_DATA", "HSPIP_DATA_DIR"):
        raw = (os.environ.get(key) or "").strip()
        if raw:
            return raw
    saved = load_saved_hspip_paths().get("data") or ""
    if saved:
        return saved
    teams = _teams_hspip_data()
    return str(teams) if teams is not None else ""


def resolve_hspip_exe(raw: str) -> dict[str, Any]:
    """Validate a user/env path. Dir -> look for HSPiP.exe; file must be named like HSPiP.exe."""
    raw = (raw or "").strip().strip('"').strip("'")
    if not raw:
        return {
            "ok": False,
            "exe": None,
            "install_dir": None,
            "message": "No HSPiP.exe path set",
        }
    p = Path(raw)
    exe: Path | None = None
    if p.is_dir():
        for name in ("HSPiP.exe", "hspip.exe", "HSPIP.exe"):
            cand = p / name
            if cand.is_file():
                exe = cand
                break
        if exe is None:
            return {
                "ok": False,
                "exe": None,
                "install_dir": p,
                "message": f"Folder found but HSPiP.exe is not inside: {p}",
            }
    elif p.is_file():
        if p.name.lower() != "hspip.exe":
            return {
                "ok": False,
                "exe": p,
                "install_dir": p.parent,
                "message": f"File exists but name is not HSPiP.exe: {p.name}",
            }
        exe = p
    else:
        return {
            "ok": False,
            "exe": None,
            "install_dir": None,
            "message": f"Path does not exist: {p}",
        }
    return {
        "ok": True,
        "exe": exe,
        "install_dir": exe.parent,
        "message": f"HSPiP.exe found: {exe}",
    }


def resolve_hspip_data(raw: str) -> dict[str, Any]:
    """Validate a .sofx data folder. Empty raw falls back to resolve_hspip_roots()."""
    raw = (raw or "").strip().strip('"').strip("'")
    extra: list[Path] = []
    if raw:
        p = Path(raw)
        if not p.exists():
            return {
                "ok": False,
                "path": p,
                "sofx_count": 0,
                "message": f"HSPIP_DATA path does not exist: {p}",
            }
        if p.is_file():
            p = p.parent
        extra.append(p)
    roots = resolve_hspip_roots(extra=extra or None)
    sofx = 0
    for r in roots:
        try:
            sofx += sum(1 for _ in r.rglob("*.sofx"))
        except OSError:
            continue
    if not roots:
        return {
            "ok": False,
            "path": Path(raw) if raw else None,
            "sofx_count": 0,
            "message": "No HSPIP_DATA folder found (env, Teams HSPiP_Data, or typed path)",
        }
    label = str(extra[0]) if extra else roots[0]
    return {
        "ok": True,
        "path": Path(label),
        "roots": [str(r) for r in roots],
        "sofx_count": sofx,
        "message": f"sofx data: {sofx} file(s) under {len(roots)} root(s)",
    }


def apply_runtime_hspip_env(exe_raw: str, data_raw: str) -> None:
    """Honor sidebar paths for the rest of this process; refresh sofx cache."""
    exe_info = resolve_hspip_exe(exe_raw)
    if exe_info.get("ok") and exe_info.get("exe") is not None:
        os.environ["HSPIP_EXE"] = str(exe_info["exe"])
        os.environ["HSPIP_PATH"] = str(exe_info["install_dir"])
    data_info = resolve_hspip_data(data_raw)
    if data_raw.strip() and data_info.get("ok") and data_info.get("path") is not None:
        os.environ["HSPIP_DATA"] = str(data_info["path"])
        os.environ["HSPIP_DATA_DIR"] = str(data_info["path"])
    clear_cache()


def hspip_gui_running() -> bool:
    """Best-effort: HSPiP.exe already running (GUI and CLI share the name)."""
    try:
        proc = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq HSPiP.exe", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    out = (proc.stdout or "").lower()
    return "hspip.exe" in out


def _parse_out_dat(path: Path) -> dict[str, Any] | None:
    """Parse HSPiP Out.dat. Returns D/P/H only when all three parse as floats."""
    if not path.is_file() or path.stat().st_size <= 0:
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    rows: list[dict[str, str]] = []
    try:
        reader = csv.DictReader(
            text.splitlines(),
            delimiter="\t",
            fieldnames=OUT_DAT_COLUMNS,
        )
        for i, row in enumerate(reader):
            if i == 0 and str(row.get("HSPiP_SMILES") or "").lower() in {
                "hspip_smiles", "smiles", "hspip smiles",
            }:
                continue
            rows.append(row)
    except Exception:
        return None
    if not rows:
        return None
    row = rows[0]
    try:
        d = float(str(row.get("D") or "").strip())
        p = float(str(row.get("P") or "").strip())
        h = float(str(row.get("H") or "").strip())
    except (TypeError, ValueError):
        return None
    rer = None
    rer_raw = str(row.get("RER") or "").strip()
    if rer_raw not in {"", "-", "nan", "None"}:
        try:
            rer = float(rer_raw)
        except ValueError:
            rer = None
    return {
        "D": d,
        "P": p,
        "H": h,
        "RER": rer,
        "HSPiP_SMILES": (row.get("HSPiP_SMILES") or "").strip(),
        "Formula": (row.get("Formula") or "").strip(),
    }


def compute_hsp_via_cli(
    smiles: str,
    exe: Path,
    *,
    timeout: int = 90,
) -> dict[str, Any]:
    """
    Best-effort SMILES -> D/P/H via licensed HSPiP.exe Y-MBSX.

    Follows vendors/cas_to_hspip/HSPiP_CLI_v7.py (cwd = install dir, read Out.dat).
    Close the HSPiP GUI first. Never invents D/P/H — parse failure is an error.
    """
    smiles = (smiles or "").strip()
    if not smiles:
        return {"ok": False, "error": "No SMILES provided. Cannot invent D/P/H."}
    if not exe or not Path(exe).is_file():
        return {"ok": False, "error": f"HSPiP.exe not found: {exe}"}
    exe = Path(exe)
    install_dir = exe.parent
    out_dat = install_dir / "Out.dat"
    prev_mtime = out_dat.stat().st_mtime if out_dat.is_file() else 0.0
    gui = hspip_gui_running()
    cmd = [str(exe), "Y-MBSX", smiles]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(install_dir),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "error": (
                "HSPiP CLI timed out. Close the HSPiP GUI (it contends with CLI), "
                "then retry. Out.dat / clipboard lock is common."
            ),
            "gui_running": gui,
        }
    except OSError as exc:
        return {"ok": False, "error": f"Failed to launch HSPiP.exe: {exc}", "gui_running": gui}

    parsed = None
    for _ in range(8):
        if out_dat.is_file() and out_dat.stat().st_mtime >= prev_mtime and out_dat.stat().st_size > 0:
            parsed = _parse_out_dat(out_dat)
            if parsed:
                break
        time.sleep(0.4)

    if not parsed:
        tail = ((proc.stderr or "") + "\n" + (proc.stdout or "")).strip()[-400:]
        hint = " Close the HSPiP GUI before CLI." if gui else ""
        extra = f" Process output: {tail}" if tail else ""
        return {
            "ok": False,
            "error": (
                "HSPiP CLI did not write a parseable Out.dat with D/P/H. "
                "Not inventing values."
                f"{hint}{extra}"
            ),
            "returncode": proc.returncode,
            "gui_running": gui,
        }
    return {
        "ok": True,
        "D": parsed["D"],
        "P": parsed["P"],
        "H": parsed["H"],
        "RER": parsed["RER"],
        "source_label": f"HSPiP CLI Y-MBSX ({exe.name})",
        "returncode": proc.returncode,
        "gui_running": gui,
    }
