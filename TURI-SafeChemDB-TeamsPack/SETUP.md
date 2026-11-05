# Setup — TURI Safe Chem DB

**Use this folder.** Copy it onto the PC and double-click the launcher. No GitHub required.

Full walkthrough: [README_START_HERE.md](README_START_HERE.md)

## Once per PC

1. Copy **`TURI-SafeChemDB-TeamsPack`** out of Teams / OneDrive onto the PC (Desktop or `C:\TURI`). Keep the whole folder together.  
2. Install Python once if needed: [python.org](https://www.python.org/downloads/) and check **Add python.exe to PATH**. See `Install_Python_for_TURI_Safe_Chem_DB.docx`.  
3. Double-click **`1_Open_Safe_Chem_DB.bat`**. The first run can take about 10 minutes and needs internet.  
4. The browser opens at http://localhost:8502. Enter a CAS (try **67-64-1** for acetone) and click **Generate**.  
   You can also upload a Safety Data Sheet PDF. Generate uses it when the sheet is clearly one chemical.

You do not need to copy `config\env.bat`. `run_doss.bat` opens the same app.

**Need:** Windows, Python 3.10 or newer, network.  
**Do not need:** GitHub, git, coding.

## HSPiP (optional)

The app looks for `HSPiP.exe` in Program Files. If it finds it, that box is filled in. The `.sofx` files are usually in the same folder. If they are not found, paste that folder in the sidebar. If this PC does not have HSPiP, leave the boxes blank. D / P / H then stay `needs_HSPiP`.

## If something goes wrong

- **Python not found** → install from python.org with PATH checked.  
- **needs_HSPiP** → optional Hansen data is not on this PC.  
- **SDS did not read, or lists several CAS numbers** → type one CAS, and share the PDF with Gabriel.  
- **Port busy** → close other Streamlit windows.  
- **Empty Fisher/TCI** → check network; leave Advanced toggles on.

## Developers

Source of truth: private repo https://github.com/glsalierno/turi-safe-chem-db — see `app\docs\TEAMS_DEPLOY.md`.
