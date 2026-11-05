TURI Safe Chem DB — start here
================================

This Teams folder is the product. You do NOT need GitHub, git, or coding.

GLOSSARY
  CAS     Chemical ID (acetone = 67-64-1)
  DoSS    Database of Safer Solvents row
  P2OASys Hazard / process score used at TURI
  SDS     Safety Data Sheet from a vendor
  HSPiP   Optional software for Hansen D/P/H numbers

WHAT YOU NEED
  - Windows PC
  - Python once from https://www.python.org/downloads/
    (check "Add python.exe to PATH")
  - Network

STEPS
  1. Copy this whole folder out of Teams / OneDrive onto the PC
     (Desktop or C:\TURI). Do not run it from the synced folder.
  2. Double-click 1_Open_Safe_Chem_DB.bat
     First run can take about 10 minutes. Leave the black window open.
  3. Browser opens (http://localhost:8502)
  4. Type a CAS, e.g. 67-64-1 for acetone, and click Generate
     Or upload an SDS PDF and click Generate.
     If the sheet has several CAS numbers or will not read, share the PDF with Gabriel.

You do not need to copy config\env.bat.
HSPiP is optional. The app looks in Program Files. If it does not find
HSPiP.exe, paste that folder in the sidebar. The .sofx files are usually
in the same folder.

TROUBLESHOOTING
  "Python was not found"  → Install Python + Add to PATH, retry
  needs_HSPiP             → Optional. Paste the HSPiP folder, or leave it blank
  SDS did not read        → Share the PDF with Gabriel
  Port in use             → Close other Safe Chem / Streamlit windows
  Empty Fisher/TCI        → Need network; leave Advanced toggles on

Developers / updates: https://github.com/glsalierno/turi-safe-chem-db (private)
Full guide: README_START_HERE.md
Setup handout (Word): TURI_Tools_Setup_Guide.docx
  (prerequisites for DoSS, GHAZ7, and auto P2OASys)
