# Install

## Requirements

- Python 3.10+ (3.11–3.13 tested)
- Network access for PubChem / Fisher / TCI enrichment
- Optional: licensed HSPiP + `.sofx` data for D/P/H/RER
- Optional: GHaz7 `p2oasys_score_lookup.sqlite` for auto P2OASys fallback

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

Small files under `data/` ship with the repo. Point `EXPERT_P2OASYS_CSV` / `P2OASYS_SCORE_LOOKUP_DB` / `HSPIP_DATA` at larger private assets as needed.
