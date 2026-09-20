# TURI Safe Chem DB (`turi-safe-chem-db`)

## Just want to run it?
**Coworkers:** use the **Teams pack** (`TURI-SafeChemDB-TeamsPack`) — sync the folder and double-click `1_Open_Safe_Chem_DB.bat`. No GitHub required.
See that pack's `README_START_HERE.md`.

## Updating the code?
Clone this public repo: https://github.com/glsalierno/turi-safe-chem-db  
This git tree is the **source of truth for developers**. Coworkers should stay on the Teams pack.

---

**TURI Safe Chem DB** is an open monorepo for safer-solvent screening and hazard enrichment:

- **DoSS on-demand** — Streamlit app that builds Database of Safer Solvents (DoSS) rows from CAS
- **P2OASys** — expert CSV + optional auto/expert SQLite score lookup (Auto6 category max convention)
- **Fisher + TCI SDS** — on-demand SDS/product enrichment (NFPA, physchem, gloves, lab $/kg when available)
- **HSPiP glue** — local `.sofx` D/P/H/RER lookup + optional licensed CLI for new CAS 

Built for TURI / UMass Lowell research workflows. Shareable code is MIT; HSPiP binaries and `.sofx` libraries are **not** included.

## Features

| Feature | Status |
|---------|--------|
| Single-CAS DoSS lookup (Streamlit, port **8502**) | Yes |
| Batch CAS mode + CSV download | Yes |
| Expert P2OASys CSV (`data/priority_expert_p2oasys_scores.csv`) | Yes |
| Bundled `data/p2oasys_score_lookup.sqlite` expert + auto (harvest) | Yes (~1,250 CAS; override `P2OASYS_SCORE_LOOKUP_DB`) |
| PubChem identity / physchem / GHS / NFPA | Yes |
| **Fisher SDS enrich** (sidebar toggle; default from `DOSS_ENABLE_FISHER`) | Yes |
| **TCI SDS enrich** (sidebar toggle; default **ON**) | Yes — best-effort |
| Optional **ECOSAR** (PyEPISuite remote; sidebar / `DOSS_ENABLE_ECOSAR`) | Opt-in — notes only; no EPA binary; does not auto-fill P2OASys Ecological |
| HSPiP `.sofx` D/P/H/RER fill | Env / sidebar `HSPIP_DATA` |
| HSPiP CLI for new CAS (Y-MBSX) | Opt-in; licensed `HSPiP.exe` |
| HSP-predicted glove polymer screen | Yes (not breakthrough-time) |
| Open vendor wrappers (`vendors/cas_to_hspip/`) | Yes |
| Batch scripts (`scripts/batch_priority_doss.py`, `fill_hspip_dph_rer.py`) | Yes |

## Quick start

```bash
cd turi-safe-chem-db
python -m venv .venv
# Windows:
.venv\Scripts\activate
pip install -r requirements.txt
# optional editable install:
# pip install -e .

# Launch DoSS (port 8502 avoids clashing with other Streamlit apps on 8501)
python scripts/run_doss_streamlit.py
# equivalent:
# streamlit run apps/doss_ondemand/app.py --server.port 8502
```

Browser: http://localhost:8502

With `PYTHONPATH` set to the repo root (or after `pip install -e .`), imports resolve as `packages.*`.

## Repo layout

```
apps/doss_ondemand/     # Streamlit UI (DoSS on-demand)
packages/doss_core/     # PubChem, Fisher, TCI, HSPiP, schema, glove HSP
packages/p2oasys_core/  # Expert/auto P2OASys lookup
data/                   # Seed CSVs + bundled P2OASys sqlite lookup/harvest
vendors/cas_to_hspip/   # Open HSPiP CLI / PubChem / MATLAB glue (no binary)
scripts/                # Batch + Streamlit launcher
docs/                   # INSTALL, HSPiP_CLI, TEAMS_DEPLOY
```

## Environment variables

| Variable | Purpose |
|----------|---------|
| `EXPERT_P2OASYS_CSV` | Path to expert P2OASys scores CSV (else `data/priority_expert_p2oasys_scores.csv`) |
| `P2OASYS_SCORE_LOOKUP_DB` | Override path to P2OASys score lookup sqlite. Default is bundled `data/p2oasys_score_lookup.sqlite` (expert harvest + auto for missing CAS). |
| `HSPIP_PATH` / `HSPIP_EXE` | HSPiP install dir or `HSPiP.exe` (sidebar prompt + CLI scripts). Placeholder: `<YOUR_HSPIP_INSTALL>` |
| `HSPIP_DATA` / `HSPIP_DATA_DIR` | Directory of licensed HSPiP `.sofx` libraries. Placeholder: `%HSPIP_DATA%` / `<YOUR_HSPIP_DATA>` |
| `DOSS_ENABLE_FISHER` | Default for Fisher SDS sidebar toggle (`1`/`0`; default on) |
| `PYTHONPATH` | Set to repo root if not using editable install |

The DoSS sidebar **HSPiP setup** section also persists exe / data paths to `config/hspip_path.txt` (gitignored) and `~/.turi-safe-chem-db/hspip_path.txt`.

## Fisher & TCI SDS enrichment

Both vendors are **intentional, shareable** on-demand enrichers (not mass scrapers):

- **Fisher** (`packages/doss_core/fisher.py`) — SDS / product page for NFPA, lab $/kg, SDS link, §9 physchem when the seed catalog has a part number. Sidebar toggle; default from `DOSS_ENABLE_FISHER`.
- **TCI** (`packages/doss_core/tci.py`) — SDS / product enrichment for NFPA, physchem, glove notes, and pricing when available. Sidebar **“On-demand TCI SDS enrich”** defaults to **ON** (`enable_tci=True`). Live HTTP may hit **Akamai / 403** blocks; when a local SDS cache is present under an optional sibling GHaz7 tree it is used as fallback. 

Seed catalogs: `data/fisher_catalog_by_cas.csv` (and optional TCI catalog files if you add them under `data/`).


## Optional ECOSAR (PyEPISuite remote)

Aquatic QSAR enrichment via the unofficial MIT package [`pyepisuite`](https://pypi.org/project/pyepisuite/) talking to a **remote EPI Suite API**.

- **Not EPA.** Unaffiliated with EPA; this repo does **not** redistribute EPA EPI Suite / ECOSAR binaries (same hard rule as HSPiP).
- Install optional deps: `pip install -r requirements-ecosar.txt` (`pyepisuite>=1.2.0`).
- Set `PYEPISUITE_MODE=remote` for API-only (the DoSS client also defaults this).
- DoSS sidebar: **Advanced / data sources → ECOSAR (PyEPISuite remote API)** (default **OFF**, or `DOSS_ENABLE_ECOSAR=1`).
- When enabled, results go into **enrichment notes only**. Values are never invented.
- **Hard rule:** do **not** map ECOSAR outputs into P2OASys Ecological subcategory scores automatically.
- Spike helper: `scripts/batch_ecosar_spike.py` → `data/ecosar_spike/` (optional artifact).

## HSPiP

**Due diligence / self-install:** This repo never ships `HSPiP.exe`, CLI licenses, or `.sofx` files. Obtain HSPiP from [hansen-solubility.com](https://www.hansen-solubility.com/HSPiP).

| Mode | When |
|------|------|
| **`.sofx` libraries** | Preferred for interactive DoSS when CAS is in curated solvent tables → D/P/H/RER |
| **CLI (`HSPiP.exe Y-MBSX`)** | Opt-in for **new CAS** missing sofx; needs licensed CLI + real SMILES (PubChem) |

- In-app **HSPiP setup** sidebar: paste path to exe or install folder; validate; optional data folder.
- **Close the HSPiP GUI** before CLI (GUI and CLI contend for locks / Out.dat / clipboard).
- **D/P/H are never invented** — missing sofx or failed CLI parse → `needs_HSPiP`.
- Open wrappers: `vendors/cas_to_hspip/` (set `PATH_TO_HSPIP_INSTALLATION` placeholders; optional RDKit via conda for CLI batch).

See [docs/HSPiP_CLI.md](docs/HSPiP_CLI.md).

## What is NOT included

- `HSPiP.exe`, license keys, install trees
- `*.sofx` solvent libraries / full harvest dumps
- Large batch report CSVs / Streamlit logs / `__pycache__`
- Guaranteed live Fisher/TCI access (network / bot-protection dependent)

## Teams pack

**Primary product for TURI coworkers** — sibling folder: **`TURI-SafeChemDB-TeamsPack`** (see [docs/TEAMS_DEPLOY.md](docs/TEAMS_DEPLOY.md)).

- `app\` mirrors this monorepo (sync with robocopy; excludes `.venv`, `__pycache__`, `.git`)
- Placeholder `HSPiP\` / `HSPiP_Data\` for licensed assets
- `run_doss.bat` launches Streamlit on port **8502**

Developers who prefer git should use this **`turi-safe-chem-db`** repo as source of truth.

## Data provenance

- **Never invent** P2OASys scores, NFPA digits, prices, or Hansen D/P/H/RER.
- Lab / bulk cost columns are **$/kg**; leave `-` when unknown.
- NFPA Health/Flame use a **precautionary max** merge across Fisher / TCI / PubChem; see **NFPA Source**.
- Glove HSP flags are **HSP-predicted** (not breakthrough-time claims); curated SDS glove material wins when present.

## Requirements

See [requirements.txt](requirements.txt). Optional:

```bash
pip install -r requirements-ecosar.txt   # optional ECOSAR / pyepisuite remote
pip install -r requirements-dev.txt   # vulture, pytest
# RDKit (vendors/cas_to_hspip CLI canonicalize only) — prefer conda:
# conda install -c conda-forge rdkit
```

DoSS core does **not** require RDKit.

## License

- **Open code** (DoSS app, packages, scripts, vendor glue): **MIT** — see [LICENSE](LICENSE).
- **Third-party:** PubChem (NCBI ToS), HSPiP proprietary (Hansen Solubility), Fisher / TCI websites (best-effort scraping; respect robots / ToS).

## Citation / acknowledgement

If you use this tooling in publications or internal reports, please acknowledge:

> Toxics Use Reduction Institute (TURI), University of Massachusetts Lowell — TURI Safe Chem DB / DoSS on-demand.

Author / maintainer GitHub: [glsalierno](https://github.com/glsalierno).

## Docs

- [docs/INSTALL.md](docs/INSTALL.md)
- [docs/HSPiP_CLI.md](docs/HSPiP_CLI.md)
- [docs/TEAMS_DEPLOY.md](docs/TEAMS_DEPLOY.md)
- [PACKAGING_NOTES.md](PACKAGING_NOTES.md)
