# TURI Safe Chem DB

On-demand chemical hazard and safer-solvent screening: enter a CAS number, get identity, GHS/physchem, expert or automatic TURI hazard scores, and optional SDS or Hansen enrichment.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Capabilities CI](https://github.com/glsalierno/turi-safe-chem-db/actions/workflows/capabilities-ci.yml/badge.svg)](https://github.com/glsalierno/turi-safe-chem-db/actions/workflows/capabilities-ci.yml)

Research software from **TURI / UMass Lowell**. This repository’s code is MIT-licensed. Licensed third-party tools (HSPiP binaries and `.sofx` libraries) are **not** redistributed here.

<!-- TODO: confirm whether a screenshot of the DoSS UI (port 8502) can be added under docs/ -->

## What it does

| Capability | Notes |
|------------|--------|
| Single-CAS lookup (Streamlit, port **8502**) | `python scripts/run_doss_streamlit.py` or `streamlit run apps/doss_ondemand/app.py --server.port 8502` |
| Searchable chemical picker | Bundled lookup covers **1,254** CAS; free-text CAS works for chemicals outside that set |
| Batch CAS mode + CSV download | Yes |
| Expert and automatic TURI hazard scores | Six science categories (Acute, Chronic, Ecological, Fate & Transport, Atmospheric, Physical), each 0–10; **overall = max** of those six (Process / Life Cycle are not in the overall). Bundled `data/p2oasys_score_lookup.sqlite`. Optional expert CSV overlay (`data/priority_expert_p2oasys_scores.csv`, sidebar toggle). Override the database path with `P2OASYS_SCORE_LOOKUP_DB`. |
| PubChem identity / physchem / GHS / NFPA | Throttle-hardened client with disk cache |
| Fisher and TCI SDS enrichment | Optional, on-demand, best-effort (live HTTP may be blocked) |
| HSPiP D/P/H/RER | Optional local `.sofx` and/or licensed CLI; not shipped |
| HSP-predicted glove polymer screen | Not a breakthrough-time claim; curated SDS glove material wins when present |

Every advertised capability is listed in [`CAPABILITIES.md`](CAPABILITIES.md) and checked by `tests/test_capabilities.py`.

## Quick start

Python **3.10+** (3.11–3.13 tested). Network access is required for live PubChem / Fisher / TCI calls. The bundled score database works offline.

```bash
git clone https://github.com/glsalierno/turi-safe-chem-db.git
cd turi-safe-chem-db
python -m venv .venv
# Windows:  .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
# optional, so `packages.*` imports resolve without PYTHONPATH:
# pip install -e .

python scripts/run_doss_streamlit.py
```

Open http://localhost:8502

Port **8502** is intentional: it avoids clashing with other Streamlit apps on 8501.

Without an editable install, set `PYTHONPATH` to the repository root.

Developer tests:

```bash
pip install -r requirements-dev.txt
# optional RDKit, only for vendors/cas_to_hspip CLI canonicalization — prefer conda:
# conda install -c conda-forge rdkit
PYTHONPATH=. pytest
PYTHONPATH=. python -m packages.capability_report
```

Last clean local run on this tree: **`57 passed, 18 skipped`** (`pytest` with `PYTHONPATH=.`).

### TURI coworkers (no Git required)

The **Teams pack** (`TURI-SafeChemDB-TeamsPack`) is the supported coworker install: sync the folder and use the pack’s `README_START_HERE.md` / `run_doss.bat` (also port 8502). This GitHub repository is the source of truth for developers. See [docs/TEAMS_DEPLOY.md](docs/TEAMS_DEPLOY.md) and [docs/START_HERE_TEAMS.md](docs/START_HERE_TEAMS.md).

## Example (one CAS)

1. Launch the app as in Quick start.
2. Pick **Acetone** from the searchable list, or enter CAS **`67-64-1`**.
3. You should see PubChem identity and GHS/physchem when the network is up.
4. From the bundled score database (offline), acetone resolves as an **expert** TURI hazard score with **overall 8** (max of the six science categories). Automatic scores, when used, are labelled with source `auto` and are **never averaged** with expert scores — expert CSV overlay wins first, then SQLite expert rows, then SQLite auto.
5. Missing evidence stays blank or is marked with an explicit gap such as `needs_HSPiP`. Values are never invented. HSP glove flags are labelled **HSP-predicted**.

Offline check (no Streamlit required):

```bash
PYTHONPATH=. python -c "from packages.p2oasys_core.lookup import resolve_p2oasys; print(resolve_p2oasys('67-64-1', expert_df=None))"
# -> {'overall': '8', 'source': 'expert', 'detail': 'sqlite:p2oasys_score_lookup.sqlite', 'name': 'Acetone'}
```

CSV export uses a DoSS-compatible column layout.

## Configuration

| Variable | Purpose |
|----------|---------|
| `P2OASYS_SCORE_LOOKUP_DB` | Override path to the bundled score-lookup SQLite (default `data/p2oasys_score_lookup.sqlite`) |
| `EXPERT_P2OASYS_CSV` | Optional expert CSV overlay (not loaded until the sidebar checkbox or an upload) |
| `HSPIP_PATH` / `HSPIP_EXE` | HSPiP install dir or `HSPiP.exe` (sidebar also prompts). Placeholder: `<YOUR_HSPIP_INSTALL>` |
| `HSPIP_DATA` / `HSPIP_DATA_DIR` | Directory of licensed HSPiP `.sofx` libraries |
| `DOSS_ENABLE_FISHER` | Default for the Fisher SDS sidebar toggle (`1`/`0`; default on) |
| `PUBCHEM_MIN_INTERVAL_S` | Minimum seconds between PubChem requests (default `0.35`) |
| `PUBCHEM_MAX_RETRIES` | Max retries on 429/503 (default `5`) |
| `PUBCHEM_CACHE_DIR` | PubChem cache directory (default `data/cache/pubchem/`) |
| `PUBCHEM_CACHE_MAX_AGE_S` | Cache TTL in seconds (default `86400`) |
| `PYTHONPATH` | Repository root, if you did not `pip install -e .` |

The in-app **HSPiP setup** section can also persist paths to `config/hspip_path.txt` (gitignored) and `~/.turi-safe-chem-db/hspip_path.txt`.

The names above are the current environment-variable identifiers in this repository. <!-- TODO: if these names are ever changed to drop the historical mark, document the new names and a compatibility alias. -->

## Outputs

- On-screen assessment for one or many CAS numbers.
- CSV download in the DoSS-shaped spreadsheet layout.
- Optional SDS-derived NFPA, physchem, glove notes, and lab $/kg when Fisher/TCI enrichment succeeds.
- Optional Hansen D/P/H/RER when HSPiP data or CLI is configured.

**Source rules:** never invent hazard scores, NFPA digits, prices, or Hansen parameters. Lab/bulk cost columns are **$/kg**, or `-` when unknown. NFPA Health/Flame use a precautionary max across Fisher / TCI / PubChem (see **NFPA Source**). Glove HSP flags are **HSP-predicted**, not breakthrough times. Automatic TURI hazard scores are labelled separately from **expert scores** (`source` is `expert` or `auto`); the two are never averaged, and expert values take precedence.

## Limits

- HSPiP.exe, CLI licenses, and `.sofx` libraries are not included. Obtain HSPiP yourself from [hansen-solubility.com](https://www.hansen-solubility.com/HSPiP). Close the HSPiP GUI before using the CLI.
- Live Fisher/TCI access is best-effort (network and bot-protection dependent). TCI may return Akamai / 403.
- PubChem is rate-limited; after retries the UI reports a throttle and batch scripts stop rather than continuing to fire requests.
- Automatic scores and HSP glove flags are not a substitute for expert review. This is research software.

## Citation

If you use this tooling in publications or internal reports, please cite the software via [`CITATION.cff`](CITATION.cff), or acknowledge:

> Toxics Use Reduction Institute (TURI), University of Massachusetts Lowell — TURI Safe Chem DB / DoSS on-demand.

Maintainer: [glsalierno](https://github.com/glsalierno).

<!-- TODO: add a Zenodo DOI when this tree is archived. -->

## License

- **Code** in this repository: **MIT** — see [LICENSE](LICENSE).
- **Third-party terms** still apply: PubChem (NCBI), HSPiP (Hansen Solubility), Fisher / TCI websites.

## Docs

- [docs/INSTALL.md](docs/INSTALL.md)
- [docs/HSPiP_CLI.md](docs/HSPiP_CLI.md)
- [docs/TEAMS_DEPLOY.md](docs/TEAMS_DEPLOY.md)
- [docs/PORTING_CHECKLIST.md](docs/PORTING_CHECKLIST.md)
- [PACKAGING_NOTES.md](PACKAGING_NOTES.md)
- [CAPABILITIES.md](CAPABILITIES.md)
