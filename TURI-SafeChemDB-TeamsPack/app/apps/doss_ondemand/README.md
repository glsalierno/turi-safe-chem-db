# DoSS on-demand

Streamlit UI for Database of Safer Solvents row generation.

## Features
- **Searchable chemical picker** from the full P2OASys universe (~1,250 chemicals)
- **Free-text CAS entry** for chemicals outside the bundled universe
- **Batch mode** for processing multiple CAS at once
- P2OASys scores from bundled SQLite (expert harvest + auto fallback)
- Optional expert CSV overlay (sidebar upload or checkbox)

## Quick start

```bash
# from repo root
python scripts/run_doss_streamlit.py
# or
streamlit run apps/doss_ondemand/app.py --server.port 8502
```

Imports use `packages.doss_core.*` and `packages.p2oasys_core.*`.
