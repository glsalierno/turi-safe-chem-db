# STATUS — turi-safe-chem-db / TURI Safe Chem DB

Canonical trees (host **Fierro22**, `67c9cbaa-689b-41cf-9c17-11543d316c1e`):
- Monorepo: `C:\Users\glsal\OneDrive - UMass Lowell\TURI\Research\QSAR\hazquery\turi-safe-chem-db`
- Teams product: `...\hazquery\TURI-SafeChemDB-TeamsPack`
- GitHub (private): https://github.com/glsalierno/turi-safe-chem-db

Product rule: **Teams pack is the coworker product**; GitHub is for code updates.
Keep Cursor posted: update this file after meaningful steps (not chat alone).

## Now
- PASS | Coworker how-to DOCX on Teams pack + `docs/` + GitHub `main` (`36448c6`)
- PASS | Keep Cursor posted STATUS.md in repo
- RUNNING | Branch `feat/p2oasys-score-lookup-db` checked out with **uncommitted** WIP (sqlite sizes, lookup.py, app.py, expert CSV, README)
- PASS | Cursor (while Grok Bot away): bundled P2OASys harvest sqlite on that feat branch (`acff086`); CAMEO NFPA local sqlite on `feat/cameo-nfpa-lookup` (`bb162a9`)
- HELD | P2OASys harvest compile append routine: `resource_exhausted` since ~2026-09-14 (separate workstream)
- NOTE | Fierro25 (`7b3409c3-…`) is connected for chat sends but hazquery tree not verified there; canonical = Fierro22

## Builds (code)
- 2026-09-13 ET | code | Initial push + Teams-first onboarding | `3920787`, `bbc1cd1` @ main | PASS
- 2026-09-13 ET | code | CAMEO NFPA 704 local sqlite lookup | branch `feat/cameo-nfpa-lookup` `bb162a9` | PASS (not merged to main)
- 2026-09-14 ET | code | Bundle P2OASys harvest lookup sqlite (~1250 CAS) for DoSS | branch `feat/p2oasys-score-lookup-db` `acff086` | PASS (not merged to main)
- 2026-09-18 ~05:27 ET | code | Coworker DOCX + STATUS.md | `main` `36448c6` + feat `c9e5603` | PASS
- 2026-09-18 ET | code | Uncommitted WIP on feat/p2oasys-score-lookup-db (larger sqlite, lookup.py, CSV) | local Fierro22 only | RUNNING / not pushed

## Builds (database)
- 2026-09-14 ET | db | Ship `data/p2oasys_score_lookup.sqlite` + `data/p2oasys_harvest.sqlite` in feat branch | PASS (bundled extract, not a server migration)
- 2026-09-13 ET | db | Ship `data/cameo_nfpa.sqlite` on cameo feat branch | PASS
- Uncommitted local growth of p2oasys sqlite files on Fierro22 feat branch | not committed | do not treat as published
- Harvest compile routine on box: FAIL resource_exhausted | not Safe Chem DB blocker

## Next
1. Review + commit or discard uncommitted feat/p2oasys WIP; open PR to main when ready
2. Decide merge of `feat/cameo-nfpa-lookup` into main / Teams pack
3. Refresh Teams pack `app\` from chosen branch; coworker smoke-test bat + DOCX
4. Optional: pause or fix harvest-compile routine resource_exhausted

## Hard rules
- No HSPiP.exe, licenses, or `.sofx` in git
- Never invent HSP / NFPA / prices
- No secrets in STATUS or git
- Do not silently ship dependency or schema/sqlite changes without STATUS lines + user ping
- Teams pack = coworker product; localhost is per-PC
