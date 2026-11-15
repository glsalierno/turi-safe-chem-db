# STATUS — turi-safe-chem-db / TURI Safe Chem DB

Canonical trees (host **windows-workstation**, `<MACHINE_ID>`):
- Monorepo: `<HAZQUERY_ROOT>\turi-safe-chem-db`
- Teams product: `...\hazquery\TURI-SafeChemDB-TeamsPack`
- GitHub (**public**): https://github.com/glsalierno/turi-safe-chem-db

Product rule: **Teams pack is the coworker product**; GitHub is for code updates.
Keep Cursor posted: update this file after meaningful steps (not chat alone).

## Now
- PASS | 2026-11-15 ET Docs/metadata: remove trademark from public prose; README quickstart + `CITATION.cff`; keep code identifiers unchanged (follow-up)
- WIP  | 2026-09-27 ET Capability registry: `capabilities.yaml`, `CAPABILITIES.md`, `test_capabilities.py`, capability_report CLI, PR template
- PASS | 2026-09-23 ET PubChem throttle hardening: rate limiting, cache, backoff+jitter, PubChemThrottledError, UI messaging, tests
- PASS | 2026-09-23 ET DoSS app now based on full score-lookup universe (~1,250 CAS), not priority-62 set
- PASS | 2026-09-23 ET Added searchable chemical picker from bundled SQLite universe
- PASS | 2026-09-23 ET Priority-62 CSV now optional overlay (sidebar toggle), not default basis
- PASS | 2026-09-23 ET Free-text CAS still works for out-of-universe lookups
- PASS | 2026-09-18 ET Repo visibility set to PUBLIC; main includes score-lookup sqlite from feat merge
- PASS | 2026-09-18 ~05:36 ET Teams pack sync @ windows-workstation from feat/p2oasys-score-lookup-db (WIP stashed; committed tree only; robocopy exit 3 = OK)
- PASS | Coworker how-to DOCX on Teams pack + `docs/` + GitHub `main` (`36448c6`)
- PASS | Keep Cursor posted STATUS.md in repo
- HELD | Score harvest compile append routine: `resource_exhausted` since ~2026-09-14 (separate workstream)
- NOTE | simulation-host (`<MACHINE_ID>`) is connected for chat sends but hazquery tree not verified there; canonical = windows-workstation

## Builds (code)
- 2026-09-23 ET | code | Full score-lookup universe picker in DoSS app; priority-62 CSV optional overlay | branch `cursor/full-universe-picker-e2cc` | PR
- 2026-09-18 ~05:36 ET | code | robocopy monorepo → TURI-SafeChemDB-TeamsPack\app (excl .git/.venv/__pycache__) | sqlite+docx+bat verified | PASS
- 2026-09-13 ET | code | Initial push + Teams-first onboarding | `3920787`, `bbc1cd1` @ main | PASS
- 2026-09-13 ET | code | CAMEO NFPA 704 local sqlite lookup | branch `feat/cameo-nfpa-lookup` `bb162a9` | PASS (not merged to main)
- 2026-09-14 ET | code | Bundle score-lookup sqlite (~1250 CAS) for DoSS | branch `feat/p2oasys-score-lookup-db` `acff086` | PASS (not merged to main)
- 2026-09-18 ~05:27 ET | code | Coworker DOCX + STATUS.md | `main` `36448c6` + feat `c9e5603` | PASS

## Builds (database)
- 2026-09-14 ET | db | Ship `data/p2oasys_score_lookup.sqlite` + `data/p2oasys_harvest.sqlite` in feat branch | PASS (bundled extract, not a server migration)
- 2026-09-13 ET | db | Ship `data/cameo_nfpa.sqlite` on cameo feat branch | PASS
- Uncommitted local growth of score-lookup sqlite files on windows-workstation feat branch | not committed | do not treat as published
- Harvest compile routine on box: FAIL resource_exhausted | not Safe Chem DB blocker

## Next
1. Review + merge `cursor/full-universe-picker-e2cc` PR (full score-lookup universe picker)
2. Decide merge of `feat/cameo-nfpa-lookup` into main / Teams pack
3. Coworker smoke-test Teams pack with new universe picker UI
4. Optional: pause or fix harvest-compile routine resource_exhausted
5. Follow-up: rename remaining code-level identifiers / env vars / UI strings that still use the historical mark (not this docs PR)

## Hard rules
- No HSPiP.exe, licenses, or `.sofx` in git
- Never invent HSP / NFPA / prices
- No secrets in STATUS or git
- Do not silently ship dependency or schema/sqlite changes without STATUS lines + user ping
- Teams pack = coworker product; localhost is per-PC
- Respect PubChem throttling: rate limit, backoff, cache-first (see [NCBI docs](https://pubchem.ncbi.nlm.nih.gov/docs/dynamic-request-throttling))
