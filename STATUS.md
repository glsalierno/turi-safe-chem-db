# STATUS — turi-safe-chem-db / TURI Safe Chem DB

Canonical trees (host **Fierro22**, `67c9cbaa-689b-41cf-9c17-11543d316c1e`):
- Monorepo: `C:\Users\glsal\OneDrive - UMass Lowell\TURI\Research\QSAR\hazquery\turi-safe-chem-db`
- Teams product: `...\hazquery\TURI-SafeChemDB-TeamsPack`
- GitHub (private, developers): https://github.com/glsalierno/turi-safe-chem-db

Product rule: **Teams pack is the coworker product**; GitHub is for code updates.

## Now
- PASS | Coworker how-to DOCX in Teams pack root + monorepo docs/
- RUNNING | Commit/push DOCX + STATUS.md to GitHub main
- PASS | Keep Cursor posted STATUS file created for this project
- HELD | P2OASys harvest compile append routine: repeated `resource_exhausted` failures since ~2026-09-14 (paused routine historically; not blocking Safe Chem DB share)
- PASS | Private GitHub `main` previously pushed (Teams-first onboarding `bbc1cd1` and earlier initial commit)

## Builds (code)
- 2026-09-13 ET | code | Initial monorepo push `turi-safe-chem-db` @ Fierro22 | artifact: GitHub `main` | PASS
- 2026-09-13 ET | code | Teams-first onboarding (START_HERE, `1_Open_Safe_Chem_DB.bat`, two-door README, softer DoSS UI) | commit `bbc1cd1` | PASS
- 2026-09-18 ~05:25 ET | code | box: `python-docx` in `/workspace/.venv-docx` | coworker DOCX `/workspace/TURI_Safe_Chem_DB_Coworker_HowTo.docx` | PASS
- 2026-09-18 ~05:27 ET | code | Copy DOCX + STATUS.md → Fierro22 Teams pack + monorepo docs/STATUS | PASS

## Builds (database)
- n/a for Safe Chem DB share pack (no app DB migrations). Expert scores ship as CSV seed under `data/`.
- P2OASys site harvest compile (separate workstream): compiled pages 1–101 historically at box `/workspace/p2oasys_site_exports/`; routine currently FAIL/resource_exhausted — do not treat as Safe Chem DB blocker.

## Next
1. Confirm DOCX present in `TURI-SafeChemDB-TeamsPack` and `turi-safe-chem-db/docs/`
2. Commit + push DOCX + STATUS.md to GitHub `main`
3. Upload/sync Teams pack (with DOCX) to the TURI shared channel; one coworker smoke-test `1_Open_Safe_Chem_DB.bat`
4. Optional: investigate/pause harvest-compile routine resource_exhausted separately

## Hard rules
- No HSPiP.exe, licenses, or `.sofx` in git
- Never invent HSP / NFPA / prices
- No secrets in STATUS or git
- Do not silently ship dependency or schema changes without STATUS lines
- Teams pack = coworker product; localhost app is per-PC, not a shared hosted URL
