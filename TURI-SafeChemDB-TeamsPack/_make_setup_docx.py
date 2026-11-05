"""One-shot generator for the setup DOCX. Run: python _make_setup_docx.py"""
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

OUT = Path(__file__).resolve().parent / "TURI_Tools_Setup_Guide.docx"


def set_run(run, bold=False, size=11, color=None):
    run.bold = bold
    run.font.size = Pt(size)
    run.font.name = "Calibri"
    if color:
        run.font.color.rgb = RGBColor(*color)


def shade_cell(cell, hex_color: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), hex_color)
    shd.set(qn("w:val"), "clear")
    tc_pr.append(shd)


def style_header_row(row) -> None:
    for cell in row.cells:
        shade_cell(cell, "1F4E79")
        for p in cell.paragraphs:
            for r in p.runs:
                r.bold = True
                r.font.color.rgb = RGBColor(255, 255, 255)
                r.font.size = Pt(10)
                r.font.name = "Calibri"


def style_body_cells(row, size=10) -> None:
    for cell in row.cells:
        for p in cell.paragraphs:
            for r in p.runs:
                r.font.size = Pt(size)
                r.font.name = "Calibri"


def main() -> None:
    doc = Document()
    for section in doc.sections:
        section.top_margin = Inches(0.85)
        section.bottom_margin = Inches(0.75)
        section.left_margin = Inches(0.9)
        section.right_margin = Inches(0.9)

    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    def h(text: str, level: int = 1):
        p = doc.add_heading(text, level=level)
        for r in p.runs:
            r.font.color.rgb = RGBColor(0x1F, 0x4E, 0x79)
        return p

    def para(text: str, bold: bool = False):
        p = doc.add_paragraph()
        r = p.add_run(text)
        set_run(r, bold=bold)
        p.paragraph_format.space_after = Pt(6)
        return p

    def bullet(text: str, bold_prefix: str | None = None):
        p = doc.add_paragraph(style="List Bullet")
        if bold_prefix:
            set_run(p.add_run(bold_prefix), bold=True)
            set_run(p.add_run(text))
        else:
            set_run(p.add_run(text))
        p.paragraph_format.space_after = Pt(2)

    def numbered(text: str):
        p = doc.add_paragraph(style="List Number")
        set_run(p.add_run(text))
        p.paragraph_format.space_after = Pt(2)

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_run(
        title.add_run("TURI Chemical Tools — Setup Guide"),
        bold=True,
        size=18,
        color=(0x1F, 0x4E, 0x79),
    )
    title.paragraph_format.space_after = Pt(4)

    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_run(
        sub.add_run(
            "Install these prerequisites once, then launch DoSS, GHAZ7, and auto P2OASys.\n"
            "You do not need GitHub, git, or programming skills."
        )
    )
    sub.paragraph_format.space_after = Pt(12)

    h("What these apps do", 1)
    bullet("Safer-solvent lookup rows (CAS → useful properties).", "DoSS — ")
    bullet(
        "Quick hazard assessment from PubChem and related sources (browser app).",
        "GHAZ7 — ",
    )
    bullet(
        "Draft P2OASys-style hazard scores for a chemical (inside GHAZ7 and related tools).",
        "Auto P2OASys — ",
    )
    p = doc.add_paragraph()
    set_run(p.add_run("Important: "), bold=True)
    set_run(
        p.add_run(
            "Each app runs on your own Windows PC and opens in your browser (localhost). "
            "Teams / OneDrive only delivers the files — it is not a shared live website."
        )
    )

    h("Glossary (5 terms)", 1)
    table = doc.add_table(rows=6, cols=2)
    table.style = "Table Grid"
    rows = [
        ("Term", "Plain English"),
        ("CAS", "A chemical’s ID number (acetone = 67-64-1)."),
        ("DoSS", "Database of Safer Solvents — a row of useful facts about a solvent."),
        ("P2OASys", "TURI hazard / process scoring (higher often means more concern)."),
        ("SDS", "Safety Data Sheet — vendor hazard and handling information."),
        ("HSPiP", "Optional licensed software for Hansen solubility numbers (D / P / H)."),
    ]
    for i, (a, b) in enumerate(rows):
        table.rows[i].cells[0].text = a
        table.rows[i].cells[1].text = b
        if i == 0:
            style_header_row(table.rows[i])
        else:
            style_body_cells(table.rows[i], size=10)
    doc.add_paragraph()

    h("Part A — Install once (shared prerequisites)", 1)
    para(
        "Do this on each Windows PC that will run the tools. Ask IT if your machine is locked down."
    )

    h("1. Sync the shared folders", 2)
    numbered(
        "Open the TURI Teams / shared channel and find the tool folders (ask Gabriel if unsure)."
    )
    numbered("Sync them with OneDrive / Teams so they appear on your PC (File Explorer).")
    numbered("Typical folders:")
    bullet("TURI-SafeChemDB-TeamsPack  →  DoSS (Safe Chem DB)")
    bullet("GHhaz7 / quick-hazard-assessment-app  →  GHAZ7 + Auto P2OASys (in the app sidebar)")
    para(
        "Copy the whole TURI-SafeChemDB-TeamsPack folder out of the Teams / OneDrive "
        "sync location onto the PC (Desktop or C:\\TURI). Keep every file together. "
        "Run the launcher from that copy. Running it inside the synced folder can make the first install fail."
    )

    h("2. Install Python (required)", 2)
    numbered(
        "Go to https://www.python.org/downloads/ and download the current Windows installer "
        "(Python 3.10 or newer is fine; 3.11–3.12 preferred)."
    )
    numbered("Run the installer.")
    numbered('On the first screen, CHECK the box: “Add python.exe to PATH”.')
    numbered('Choose “Install Now” (or “Install for all users” if IT prefers).')
    numbered("Close and reopen any black command windows after installing.")
    p = doc.add_paragraph()
    set_run(p.add_run("Quick check: "), bold=True)
    set_run(
        p.add_run(
            "Open Command Prompt, type  python --version  and press Enter. "
            "You should see a version number, not “Python was not found”."
        )
    )

    h("3. Network", 2)
    para(
        "You need internet access for PubChem and optional vendor lookups (Fisher / TCI). "
        "Offline campus networks may need IT allow-listing."
    )

    h("4. Optional extras (only if your team uses them)", 2)
    bullet(
        "Licensed HSPiP install + .sofx libraries (for D / P / H in DoSS). "
        "The app looks in Program Files. If it does not find HSPiP.exe, paste that folder in the sidebar. "
        "The .sofx files are usually in the same folder. Leave the boxes blank if this PC does not have HSPiP.",
        "HSPiP — ",
    )
    bullet(
        "EPA OPERA install (for some QSAR predictions in GHAZ7 / hazard workflows). "
        "Often under C:\\Program Files\\OPERA\\. Skip unless someone asked you to.",
        "OPERA — ",
    )
    bullet(
        "Tesseract / Poppler (only if you OCR scanned SDS PDFs in GHAZ7). Skip for basic CAS lookups.",
        "OCR tools — ",
    )

    h("Part B — Launch DoSS (Safe Chem DB)", 1)
    para("Folder: TURI-SafeChemDB-TeamsPack")
    numbered(
        "Use the copy of TURI-SafeChemDB-TeamsPack that is outside the Teams / OneDrive sync folder. "
        "You do not need to copy config\\env.bat."
    )
    numbered("Double-click 1_Open_Safe_Chem_DB.bat  (same as run_doss.bat).")
    numbered(
        "First run may take several minutes while Python packages install. Leave the black window open."
    )
    numbered("Your browser should open http://localhost:8502")
    numbered(
        "Try CAS 67-64-1 (acetone) and click Generate. "
        "You can also upload a Safety Data Sheet PDF and click Generate. "
        "The file is used when it is clearly one chemical. "
        "If it lists several CAS numbers or cannot be read, share the PDF with Gabriel."
    )
    p = doc.add_paragraph()
    set_run(p.add_run("Stop: "), bold=True)
    set_run(p.add_run("Close the black terminal window (or press Ctrl+C) when finished."))

    h("Part C — Launch GHAZ7 (Quick Hazard Assessment)", 1)
    para(
        "Folder: quick-hazard-assessment-app (GHAZ7). "
        "Ask Gabriel for the exact Teams / synced path if you do not see it."
    )
    numbered("Open that folder in File Explorer.")
    numbered(
        "First time only: if a teammate gave you a “create venv” instruction, follow it; "
        "otherwise try the launcher first."
    )
    numbered("Double-click run_hazard_app.bat")
    numbered("Browser: http://localhost:8501")
    numbered("Enter a CAS or chemical name and generate a hazard report.")
    p = doc.add_paragraph()
    set_run(p.add_run("If the black window says Streamlit / packages are missing: "), bold=True)
    set_run(
        p.add_run(
            "ask Gabriel or IT to create the app virtual environment once "
            "(python -m venv .venv, then pip install -r requirements.txt). "
            "Coworkers should not need to type this regularly."
        )
    )

    h("Part D — Launch Auto P2OASys", 1)
    para("Auto P2OASys is the automated / draft P2OASys scoring path. For most coworkers it lives inside GHAZ7:")
    numbered("Start GHAZ7 as in Part C (http://localhost:8501).")
    numbered('In the left sidebar, open the page “P2OASys Assessment” (or similarly named).')
    numbered("Enter a CAS (optional SDS), click Generate draft, then review scores.")
    para(
        "Power users / developers may also run command-line scorers in the hazquery project "
        "(p2oasys_scorer / fast_p2oasys). That path is optional and not required for the browser workflow."
    )

    h("Ports cheat sheet", 1)
    t2 = doc.add_table(rows=4, cols=3)
    t2.style = "Table Grid"
    data2 = [
        ("App", "Launcher", "Browser address"),
        ("DoSS", "1_Open_Safe_Chem_DB.bat", "http://localhost:8502"),
        ("GHAZ7", "run_hazard_app.bat", "http://localhost:8501"),
        ("Auto P2OASys", "Inside GHAZ7 sidebar", "http://localhost:8501 (same window)"),
    ]
    for i, row in enumerate(data2):
        for j, val in enumerate(row):
            t2.rows[i].cells[j].text = val
        if i == 0:
            style_header_row(t2.rows[i])
        else:
            style_body_cells(t2.rows[i], size=10)
    doc.add_paragraph()

    h("Troubleshooting", 1)
    t3 = doc.add_table(rows=7, cols=2)
    t3.style = "Table Grid"
    tr = [
        ("What you see", "What to try"),
        (
            "Python was not found",
            "Reinstall Python from python.org and CHECK “Add python.exe to PATH”. Close and reopen the launcher.",
        ),
        (
            "Browser never opens / blank page",
            "Wait for the black window to finish installing. Then open the localhost link yourself.",
        ),
        (
            "Port already in use",
            "Close other Safe Chem / Streamlit / hazard windows. Only one app per port at a time.",
        ),
        (
            "needs_HSPiP",
            "Optional. Paste the folder that contains HSPiP.exe, or leave D/P/H as-is. The .sofx files are usually in that same folder.",
        ),
        (
            "Empty Fisher / TCI columns",
            "Need network. In DoSS, open Advanced / data sources and leave vendor toggles on.",
        ),
        (
            "pip / Streamlit errors on first run",
            "Stay on network, retry the .bat once. If it still fails, contact Gabriel — do not debug GitHub.",
        ),
    ]
    for i, (a, b) in enumerate(tr):
        t3.rows[i].cells[0].text = a
        t3.rows[i].cells[1].text = b
        if i == 0:
            style_header_row(t3.rows[i])
        else:
            style_body_cells(t3.rows[i], size=9)
    doc.add_paragraph()

    h("Support", 1)
    para("Questions or blocked installs: ask Gabriel (not “file a pull request”).")
    para(
        "Developers / code updates: private GitHub turi-safe-chem-db and the hazquery / GHAZ7 trees. "
        "Coworkers stay on synced Teams folders + double-click launchers."
    )

    footer = doc.add_paragraph()
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_run(
        footer.add_run(
            "TURI — Pollution Prevention / Safer Alternatives tools — setup guide"
        ),
        size=9,
        color=(0x66, 0x66, 0x66),
    )

    doc.save(OUT)
    print(f"Wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
