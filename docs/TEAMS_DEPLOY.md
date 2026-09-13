# Teams / shared-drive deploy

## Product vs source of truth

| Audience | Use this |
|----------|----------|
| **TURI coworkers (primary product)** | **`TURI-SafeChemDB-TeamsPack`** — sync via Teams / OneDrive, double-click `1_Open_Safe_Chem_DB.bat`. No GitHub required. Start at the pack’s `README_START_HERE.md` (also mirrored here as [START_HERE_TEAMS.md](START_HERE_TEAMS.md)). |
| **Developers** | This git repo **`turi-safe-chem-db`** — clone, edit, PR, push. Source of truth for code. |

Do **not** treat long-term edits in the Teams `app\` copy as the main workflow; sync from git after merging.

## Mapping

| Teams pack | Monorepo (`turi-safe-chem-db`) |
|------------|-------------------------------|
| `app\` | Full copy of this repo tree |
| `config\env.bat.example` | Sets `HSPIP_PATH`, `HSPIP_DATA`, `EXPERT_P2OASYS_CSV`, `PYTHONPATH` |
| `HSPiP\` | Placeholder for licensed install (not in git) |
| `HSPiP_Data\` | Placeholder for `.sofx` libraries |
| `cache\` | Local runtime cache |
| `1_Open_Safe_Chem_DB.bat` | Friendly launcher (calls `run_doss.bat`) |
| `run_doss.bat` | Creates `.venv`, loads env, launches Streamlit on **8502** |
| `README_START_HERE.md` / `0_Read_Me_First.txt` | Non-programmer onboarding |
| `SETUP_FOR_COWORKERS.md` | Short Teams-first checklist |

## Coworker flow

1. Sync `TURI-SafeChemDB-TeamsPack` to Teams / OneDrive.
2. Copy `config\env.bat.example` → `config\env.bat` and edit paths if needed.
3. Optional: place licensed HSPiP under `HSPiP\` (or point `HSPIP_PATH`).
4. Optional: place `.sofx` libraries under `HSPiP_Data\` (or point `HSPIP_DATA`).
5. Double-click **`1_Open_Safe_Chem_DB.bat`** (or `run_doss.bat`).
6. In the DoSS sidebar, set **Where is HSPiP installed on this PC?** if you need CLI for new CAS (persisted locally; not committed).

## Syncing pack from git (maintainers)

After changing this monorepo, robocopy into the Teams pack `app\` excluding `.venv`, `__pycache__`, and `.git`. Pack-root START_HERE / launcher bats live only in the Teams pack (documented here via `START_HERE_TEAMS.md`).
