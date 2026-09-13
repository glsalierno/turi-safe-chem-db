# PACKAGING_NOTES — TURI Safe Chem DB (`turi-safe-chem-db`)

Prep for first GitHub push as **turi-safe-chem-db** / TURI Safe Chem DB (Fierro22 assembly host; no hostnames in shipped code).

## Included

- DoSS Streamlit app → `apps/doss_ondemand/app.py` (`packages.*` imports)
- Core → `packages/doss_core/` (schema, pubchem, **fisher**, **tci**, sigma, hspip, glove_hsp)
- P2OASys → `packages/p2oasys_core/lookup.py`
- Seed data → `data/*.csv`, `data/priority_cas_list.txt`
- Batch → `scripts/batch_priority_doss.py`, `scripts/fill_hspip_dph_rer.py`
- Open HSPiP glue → `vendors/cas_to_hspip/` (py/m/README/LICENSE only)
- Docs, MIT LICENSE, .gitignore, requirements.txt, requirements-dev.txt, pyproject.toml

## Intentionally kept (not dead)

- **TCI SDS enrich** (`packages/doss_core/tci.py`) + sidebar `enable_tci=True` — shareable on-demand feature alongside Fisher. Live Akamai/403 may block; local sibling cache used when present. Never invents values.
- Fisher SDS enrich (`packages/doss_core/fisher.py`) + `DOSS_ENABLE_FISHER`.

## Excluded

- `__pycache__/`, `*.pyc`, streamlit logs, `*.pid`, batch logs
- `priority62_*.csv` run artifacts, harvest dumps, GHhaz* trees
- HSPiP binaries / `*.sofx` / license keys
- Live `hazquery/doss-ondemand` working app (not deleted)

## Anonymize (2026-09-13)

- Removed hardcoded `<USER_HOME>\OneDrive\...` HSPiP Data fallbacks from `hspip.py` and `fill_hspip_dph_rer.py` → env + Teams sibling only (`%HSPIP_DATA%`, `<YOUR_HSPIP_DATA>`).
- SQLite lookup prefers `P2OASYS_SCORE_LOOKUP_DB`; documented relative example without usernames.
- `GHAZ7_ROOT` remains a **relative** sibling path for optional TCI catalog/SDS cache only (no home-dir strings).
- Removed personal hostname strings from fill-script help/messages.
- App footer no longer prints absolute lookup DB paths.
- Author strings may remain as GitHub handle `glsalierno` / “Gabriel Salierno / TURI” in LICENSE — no home directory paths.

## Vulture (conservative)

Ran vulture (min confidence 60–100). **Removed / renamed only clearly unused:**

- `pubchem.parse_numeric_with_unit` unused param → `_target_unit`

**Left intentionally (list here; do not delete without review):**

- `glove_hsp.GLOVE_POLYMER_HSP_1HR`, `glove_hsp_details` — alternate API
- `hspip.format_hsp_number` — helper for callers/scripts
- `schema.INTERNAL_KEYS`, `validate_row` — schema helpers
- Streamlit stub `*a` in `batch_priority_doss.py` — required for CLI stub
- `app.py` unused `col2` — layout placeholder
- `sqlite3.Row.row_factory` — false positive

## Residual risks

- `Program Files\Hansen-Solubility*\HSPiP` CLI dir candidates in fill script (machine-common, no username) — OK.
- Relative `GHAZ7_ROOT` may resolve to a developer’s hazquery tree when present; override catalogs via `data/` or env as needed.
- TCI/Fisher live HTTP best-effort; bot protection can fail closed (empty fields, not invented).
- Vendors/cas_to_hspip still need user to set `PATH_TO_HSPIP_INSTALLATION` before CLI batch.
