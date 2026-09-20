# STATUS — turi-safe-chem-db / TURI Safe Chem DB

Canonical trees (host **Fierro22**, `67c9cbaa-689b-41cf-9c17-11543d316c1e`):
- Monorepo: `C:\Users\glsal\OneDrive - UMass Lowell\TURI\Research\QSAR\hazquery\turi-safe-chem-db`
- Teams product: `...\hazquery\TURI-SafeChemDB-TeamsPack`
- GitHub (**public**): https://github.com/glsalierno/turi-safe-chem-db

Product rule: **Teams pack is the coworker product**; GitHub is for code updates.
Keep Cursor posted: update this file after meaningful steps (not chat alone).

## Now
- PASS | 2026-09-20 ET Teams pack sync from `feat/ecosar-pyepisuite` (`4673bb3` tree) → `TURI-SafeChemDB-TeamsPackpp` (robocopy exit 3 OK; WIP sqlite/lookup stashed during sync)
- PASS | 2026-09-20 ET Teams pack `app\.venv` recreated on Python 3.13 + `requirements.txt` + `requirements-ecosar.txt` (pyepisuite); acetone ECOSAR smoke PASS
- PASS | 2026-09-20 ET Local DoSS restarted on http://localhost:8502 from monorepo `apps/doss_ondemand/app.py` (ECOSAR sidebar available)
- PASS | 2026-09-20 ET live-solvent-assess local tree wired with ecosar.py + app toggle (not pushed to GitHub yet)

## Builds (code)
- 2026-09-20 ET | code | Teams pack robocopy + venv recreate (py3.13+pyepisuite) + DoSS :8502 restart; LSA local ecosar wire | Fierro22 | PASS
- 2026-09-20 ET | code | ECOSAR pyepisuite remote client + DoSS wire (sidebar `enable_ecosar` / `DOSS_ENABLE_ECOSAR`; notes only) | `feat/ecosar-pyepisuite` `910c3d5` pushed | PASS
- 2026-09-18 ~05:36 ET | code | robocopy monorepo → TURI-SafeChemDB-TeamsPack\app (excl .git/.venv/__pycache__) | sqlite+docx+bat verified | PASS
- 2026-09-13 ET | code | Initial push + Teams-first onboarding | `3920787`, `bbc1cd1` @ main | PASS
- 2026-09-13 ET | code | CAMEO NFPA 704 local sqlite lookup | branch `feat/cameo-nfpa-lookup` `bb162a9` | PASS (not merged to main)
- 2026-09-14 ET | code | Bundle P2OASys harvest lookup sqlite (~1250 CAS) for DoSS | branch `feat/p2oasys-score-lookup-db` `acff086` | PASS (not merged to main)
- 2026-09-18 ~05:27 ET | code | Coworker DOCX + STATUS.md | `main` `36448c6` + feat `c9e5603` | PASS
- 2026-09-18 ET | code | Uncommitted WIP on feat/p2oasys-score-lookup-db (larger sqlite, lookup.py, CSV) | local Fierro22 only | RUNNING / not pushed

## Builds (database)
- 2026-09-20 ET | db | Spike CSV/JSON under `data/ecosar_spike/` (optional artifact; keep small `summary.json` + csv if <2MB; huge dumps stay gitignored) | PASS on Fierro22 spike
- 2026-09-14 ET | db | Ship `data/p2oasys_score_lookup.sqlite` + `data/p2oasys_harvest.sqlite` in feat branch | PASS (bundled extract, not a server migration)
- 2026-09-13 ET | db | Ship `data/cameo_nfpa.sqlite` on cameo feat branch | PASS
- Uncommitted local growth of p2oasys sqlite files on Fierro22 feat branch | not committed | do not treat as published
- Harvest compile routine on box: FAIL resource_exhausted | not Safe Chem DB blocker

## Next
1. Review + commit or discard uncommitted feat/p2oasys WIP; open PR to main when ready
2. Decide merge of `feat/cameo-nfpa-lookup` into main / Teams pack
3. Coworker smoke-test `1_Open_Safe_Chem_DB.bat` + DOCX (Teams pack refreshed 2026-09-18)
4. Optional: pause or fix harvest-compile routine resource_exhausted
5. Open PR `feat/ecosar-pyepisuite` → main; optional push LSA ecosar mirror; coworker smoke `1_Open_Safe_Chem_DB.bat`

## Hard rules
- No HSPiP.exe, licenses, or `.sofx` in git
- **No EPA EPI Suite / ECOSAR binaries** in git — optional pyepisuite remote API only
- Never invent HSP / NFPA / prices / ECOSAR values
- Do **not** auto-map ECOSAR → P2OASys Ecological subcategory scores
- No secrets in STATUS or git
- Do not silently ship dependency or schema/sqlite changes without STATUS lines + user ping
- Teams pack = coworker product; localhost is per-PC
