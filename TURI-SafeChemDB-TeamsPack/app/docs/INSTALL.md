# Install

## Requirements

- Python 3.10+ (3.11–3.13 tested)
- Network access for PubChem / Fisher / TCI enrichment
- Optional: licensed HSPiP + `.sofx` data for D/P/H/RER
- Bundled `data/p2oasys_score_lookup.sqlite` for expert harvest + auto P2OASys (override with `P2OASYS_SCORE_LOOKUP_DB`)

## Steps

```bash
cd turi-safe-chem-db
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
# optional editable install:
pip install -e .
```

Without editable install, set `PYTHONPATH` to the repo root:

```bat
set PYTHONPATH=C:\path\to\turi-safe-chem-db
```

## Run

```bash
python scripts/run_doss_streamlit.py
```

Browser: http://localhost:8502

## Data seeds

Seed CSVs and the P2OASys lookup/harvest sqlite files ship under `data/`. Point `EXPERT_P2OASYS_CSV` / `P2OASYS_SCORE_LOOKUP_DB` / `HSPIP_DATA` at overrides as needed.
