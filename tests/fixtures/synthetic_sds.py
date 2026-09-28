"""
SYNTHETIC SDS FIXTURE HELPER - written for the turi-safe-chem-db PR #12 SDS port.

NOT copied from GHaz7 and NOT derived from any vendor SDS. All text below is INVENTED
for testing. Nothing here is a real product or real safety data. Safe to commit to the repo.

Provides:
  write_text_pdf(path, lines)  - dependency-free minimal PDF writer (Helvetica text, no reportlab)
  SYNTH_PURE                   - single-substance SDS text with known values in sections 2/8/9/10/11/12/14 + NFPA
  SYNTH_MIX                    - 37% solution SDS (3 CAS in section 3) -> must trigger the mixture flag

Verified on the box (Python 3.13, pypdf 6.x): pypdf.PdfReader(...).pages[i].extract_text()
returns the lines verbatim, one per line, so the PDF round-trip can be asserted exactly.
"""
from __future__ import annotations

from pathlib import Path

__all__ = ["write_text_pdf", "SYNTH_PURE", "SYNTH_MIX"]

def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

def write_text_pdf(path: Path, lines: list[str], lines_per_page: int = 60) -> Path:
    """Write a minimal PDF with the given lines of text."""
    pages = [lines[i:i + lines_per_page] for i in range(0, len(lines), lines_per_page)] or [[]]
    objs: list[bytes] = []
    kids = []
    body = []
    for pi, pg in enumerate(pages):
        content_num = 4 + pi * 2
        page_num = content_num + 1
        kids.append(page_num)
        ops = ["BT", "/F1 9 Tf", "11 TL", "40 800 Td"]
        for ln in pg:
            ops.append(f"({_esc(ln)}) Tj T*")
        ops.append("ET")
        stream = "\n".join(ops).encode("latin-1", "replace")
        body.append((content_num, b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"))
        body.append((page_num, (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                                f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_num} 0 R >>").encode()))
    head = [
        (1, b"<< /Type /Catalog /Pages 2 0 R >>"),
        (2, ("<< /Type /Pages /Kids [" + " ".join(f"{k} 0 R" for k in kids) + f"] /Count {len(kids)} >>").encode()),
        (3, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"),
    ]
    allobjs = sorted(head + body)
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = {}
    for num, data in allobjs:
        offsets[num] = len(out)
        out += f"{num} 0 obj\n".encode() + data + b"\nendobj\n"
    xref = len(out)
    n = len(allobjs) + 1
    out += f"xref\n0 {n}\n0000000000 65535 f \n".encode()
    for num in range(1, n):
        out += f"{offsets[num]:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {n} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(bytes(out))
    return path

SYNTH_PURE = """SYNTHETIC TEST SDS - INVENTED DATA - NOT A REAL PRODUCT - DO NOT USE FOR SAFETY DECISIONS
SECTION 1: Identification
Product name: Synthetica Testol (synthetic fixture)
CAS No.: 67-64-1
Supplier: Example Test Vendor (fictional)
SECTION 2: Hazards identification
Signal word: Danger
H225 Highly flammable liquid and vapour.
H319 Causes serious eye irritation.
H336 May cause drowsiness or dizziness.
H412 Harmful to aquatic life with long lasting effects.
P210 Keep away from heat.
NFPA Health: 2 Flammability: 3 Instability: 0
SECTION 3: Composition/information on ingredients
Synthetica Testol  CAS 67-64-1  >= 99 %
SECTION 8: Exposure controls/personal protection
OSHA PEL TWA 1000 ppm
Hand protection: butyl rubber gloves
SECTION 9: Physical and chemical properties
Physical state: Liquid
Odor: Pungent, fruity
pH: 7.0 (10 g/L, 20 C)
Flash point: -18 C (closed cup)
Boiling point: 56 C
Vapor pressure: 184 mmHg at 20 C
SECTION 10: Stability and reactivity
Reactivity: Stable under normal conditions.
Incompatible materials: Strong oxidizing agents.
SECTION 11: Toxicological information
Acute toxicity: LD50 Oral - Rat - 5800 mg/kg
LD50 Dermal - Rabbit - 20000 mg/kg
LC50 Inhalation - Rat - 4 h - 50100 ppm
Carcinogenicity: No component is listed by IARC.
SECTION 12: Ecological information
Toxicity to fish: LC50 - Oncorhynchus mykiss (rainbow trout) - 5540 mg/L - 96 h
Toxicity to daphnia: EC50 - Daphnia magna - 8800 mg/L - 48 h
NOEC - Daphnia magna - 2212 mg/L - 21 d
Persistence and degradability: Readily biodegradable.
Bioaccumulative potential: BCF 0.69
SECTION 13: Disposal considerations
SECTION 14: Transport information
UN 1090 Class 3 Packing group: II
SECTION 15: Regulatory information
SECTION 16: Other information
"""

SYNTH_MIX = """SYNTHETIC TEST SDS - INVENTED DATA - NOT A REAL PRODUCT
SECTION 1: Identification
Product name: Formaldehyde solution 37% (synthetic fixture)
SECTION 2: Hazards identification
Signal word: Danger
H301 Toxic if swallowed. H314 Causes severe skin burns and eye damage. H317 H341 H350
SECTION 3: Composition/information on ingredients
Formaldehyde  CAS 50-00-0  37 %
Methanol  CAS 67-56-1  10 - 15 %
Water  CAS 7732-18-5  balance
SECTION 9: Physical and chemical properties
Flash point: 64 C
SECTION 11: Toxicological information
LD50 Oral - Rat - 100 mg/kg
SECTION 12: Ecological information
SECTION 14: Transport information
UN 2209 Class 8
"""

# Synthetic SDS with estimated/ECOSAR values to test predicted flag
SYNTH_ESTIMATED = """SYNTHETIC TEST SDS - INVENTED DATA - NOT A REAL PRODUCT
SECTION 1: Identification
Product name: Estimated Testol (synthetic fixture)
CAS No.: 12345-67-8
SECTION 2: Hazards identification
H302 H315
SECTION 9: Physical and chemical properties
Flash point: 45 C
SECTION 11: Toxicological information
LD50 Oral - Rat - 2000 mg/kg
SECTION 12: Ecological information
Toxicity to fish: LC50 (estimated) - 100 mg/L - 96 h (ECOSAR predicted)
NOEC - estimated QSAR value - 50 mg/L
SECTION 14: Transport information
"""
