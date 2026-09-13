# Teams / shared-drive deploy

The sibling folder **`TURI-SafeChemDB-TeamsPack`** is a drop-in pack for TURI Teams / OneDrive shared drive.

## Mapping

| Teams pack | Monorepo (`turi-safe-chem-db`) |
|------------|-------------------------------|
| `app\` | Full copy of this repo tree |
| `config\env.bat.example` | Sets `HSPIP_PATH`, `HSPIP_DATA`, `EXPERT_P2OASYS_CSV`, `PYTHONPATH` |
| `HSPiP\` | Placeholder for licensed install (not in git) |
| `HSPiP_Data\` | Placeholder for `.sofx` libraries |
| `cache\` | Local runtime cache |
| `run_doss.bat` | Creates `.venv`, loads env, launches Streamlit on **8502** |
| `SETUP_FOR_COWORKERS.md` | Human setup checklist |

## Coworker flow

1. Upload / sync `TURI-SafeChemDB-TeamsPack` to Teams.
2. Copy `config\env.bat.example` → `config\env.bat` and edit paths.
3. Place licensed HSPiP under `HSPiP\` (or point `HSPIP_PATH` elsewhere).
4. Place `.sofx` libraries under `HSPiP_Data\` (or point `HSPIP_DATA`).
5. Double-click `run_doss.bat`.
6. In the DoSS sidebar **HSPiP setup**, confirm or paste the path to `HSPiP.exe` (persisted locally; not committed).

Developers who prefer git should clone/push **`turi-safe-chem-db`** instead of editing the Teams copy long-term.
