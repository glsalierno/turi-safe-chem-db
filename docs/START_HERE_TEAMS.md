# TURI Safe Chem DB — start here

**This Teams folder is the product.** Sync it, double-click the launcher, and look up a chemical. You do **not** need GitHub, git, or coding skills.

## Quick glossary (5 terms)

| Term | Plain English |
|------|----------------|
| **CAS** | A chemical’s ID number (example: acetone is **67-64-1**). |
| **DoSS** | Database of Safer Solvents — a row of useful facts about a solvent. |
| **P2OASys** | A hazard / process score used at TURI (higher can mean more concern). |
| **SDS** | Safety Data Sheet — the vendor’s official hazard and handling info. |
| **HSPiP** | Optional licensed software for Hansen solubility numbers (D / P / H). |

## What you need

- A **Windows** PC  
- **Python** installed once from [python.org](https://www.python.org/downloads/) — check **“Add python.exe to PATH”** during setup  
- A working **network** (lookups talk to PubChem and optional vendor sites)

## What you do **not** need

- GitHub account  
- git  
- Any programming or terminal skills  

## Big steps

1. **Sync this folder** (Teams / OneDrive) so the whole `TURI-SafeChemDB-TeamsPack` tree is on your PC.  
2. **Copy the env file once:**  
   `config\env.bat.example` → `config\env.bat`  
   (You can leave most lines alone unless someone told you to change paths.)  
3. **Optional — HSPiP data:** if your team uses HSPiP, put the licensed install under `HSPiP\` and `.sofx` libraries under `HSPiP_Data\` (or set paths inside `env.bat`). Skip this if you only need basic lookups.  
4. **Double-click** `1_Open_Safe_Chem_DB.bat`  
   (First run may take a few minutes while Python packages install. That is normal.)  
5. Your **browser** opens (usually http://localhost:8502).  
6. **Type a CAS** — try acetone: **67-64-1** — then click **Generate Row**.

You can also use `run_doss.bat`; it does the same thing.

## Troubleshooting (plain language)

| What you see | What to try |
|--------------|-------------|
| “Python was not found” | Install Python from python.org and turn on **Add to PATH**. Close and reopen the launcher. |
| Browser never opens / page blank | Wait for the black window to finish installing. Then open http://localhost:8502 yourself. |
| D / P / H say `needs_HSPiP` | Hansen numbers need HSPiP data on this PC. Ask a teammate for the licensed data folder, or leave those cells as-is. |
| “Port already in use” | Something else is using 8502. Close other Safe Chem / Streamlit windows, or ask IT to free the port. |
| Fisher / TCI columns empty | Need network. In the app, open **Advanced / data sources** and leave the vendor toggles on. |
| HSPiP CLI button fails | Close the HSPiP desktop program first; CLI needs its own license for brand-new chemicals. |

## Developers / updates

Code updates live in the private GitHub repo:  
https://github.com/glsalierno/turi-safe-chem-db  

Coworkers: stay on this **Teams pack**. Developers: clone that repo.


**Word guide:** docs/TURI_Safe_Chem_DB_Coworker_HowTo.docx (also in the Teams pack root).

