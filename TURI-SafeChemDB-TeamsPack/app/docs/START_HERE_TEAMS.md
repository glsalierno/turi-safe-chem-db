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

1. **Copy this whole folder** out of the Teams / OneDrive sync folder onto the PC (Desktop or `C:\TURI` is fine). Keep every file together. Running it inside the synced folder can make the first install fail.  
2. **Double-click** `1_Open_Safe_Chem_DB.bat`  
   (First run can take about 10 minutes while Python packages install. Leave the black window open. You need internet.)  
3. Your **browser** opens at http://localhost:8502.  
4. **Type a CAS** — try acetone: **67-64-1** — then click **Generate**.  
   Or upload a Safety Data Sheet PDF and click **Generate**. The app uses the file when it clearly belongs to one chemical. If the sheet lists several CAS numbers or cannot be read, share that PDF with Gabriel.

`run_doss.bat` opens the same app. You do not need to copy `config\env.bat`.

## Troubleshooting (plain language)

| What you see | What to try |
|--------------|-------------|
| “Python was not found” | Install Python from python.org and turn on **Add to PATH**. Close and reopen the launcher. |
| Browser never opens / page blank | Wait for the black window to finish installing. Then open http://localhost:8502 yourself. |
| D / P / H say `needs_HSPiP` | Optional. The app looks for HSPiP in Program Files. If it is not there, paste the folder that contains `HSPiP.exe`. The `.sofx` files are usually in that same folder. |
| “Port already in use” | Something else is using 8502. Close other Safe Chem / Streamlit windows, or ask IT to free the port. |
| Fisher / TCI columns empty | Need network. In the app, open **Advanced / data sources** and leave the vendor toggles on. |
| HSPiP CLI button fails | Close the HSPiP desktop program first; CLI needs its own license for brand-new chemicals. |

## Developers / updates

Code updates live in the private GitHub repo:  
https://github.com/glsalierno/turi-safe-chem-db  

Coworkers: stay on this **Teams pack**. Developers: clone that repo.


**Word guide:** docs/TURI_Safe_Chem_DB_HowTo.docx (also in the Teams pack root).

