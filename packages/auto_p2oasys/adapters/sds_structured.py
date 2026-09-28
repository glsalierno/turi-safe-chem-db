"""
Structured SDS extraction - ported from GHaz7 sds_structured.py (Gabriel Salierno), offline subset.

Parses SDS sections 2/5/7/8/9/10/11/12/14/15 plus NFPA into structured dicts.
Includes bug fixes from the PR #12 brief.

Bug fixes applied:
1. _tox_numbers: classify route using matched line only, not context window
2. _NFPA_RE: explicit labelled captures for Health, Fire, Instability
3. _section_after_label: parse same line first, not next line
4. Section 12: keep all aquatic hits with species, duration, endpoint
5. Added NOEC regex and pH/Odor parsing
6. GHS H-codes extended to H420
7. Section 12 estimated/QSAR values flagged as predicted
"""
from __future__ import annotations

import re
from typing import Any, Optional

# GHS H-code set extended to H420 (fix bug 7)
_GHS_H_CODES_SET = frozenset(f"H{i:03d}" for i in range(200, 421))

_H_RE = re.compile(r"\bH\d{3}[A-Z]?\b", re.I)
_P_RE = re.compile(r"\bP\d{3}(?:\+P\d{3})*\b", re.I)
_UN_RE = re.compile(r"\bUN\s*(\d{3,5})\b", re.I)

# Fixed NFPA pattern with explicit labelled captures (fix bug 2)
_NFPA_HEALTH_RE = re.compile(r"(?:NFPA[^\n]{0,30})?Health[:\s]*([0-4])", re.I)
_NFPA_FIRE_RE = re.compile(r"(?:NFPA[^\n]{0,30})?(?:Flammability|Fire)[:\s]*([0-4])", re.I)
_NFPA_INSTAB_RE = re.compile(r"(?:NFPA[^\n]{0,30})?(?:Instability|Reactivity)[:\s]*([0-4])", re.I)
_NFPA_SPECIAL_RE = re.compile(r"(?:NFPA[^\n]{0,30})?Special[:\s]*(\w+)", re.I)

_LIMIT_LINE = re.compile(
    r"(?P<label>OSHA\s*PEL|NIOSH\s*REL|TLV|STEL|Ceiling|IDLH|TWA|WEEL)[^\n]{0,80}?"
    r"(?P<val>\d+(?:\.\d+)?)\s*(?P<unit>ppm|mg/m3|mg/m³)",
    re.I,
)

# Fixed LD50/LC50 patterns - use line-based context (fix bug 1)
# Fix #3: Added g/kg pattern, Fix #8: Added qualifier capture
_LD50_LINE_RE = re.compile(
    r"(?P<line>[^\n]*\bLD\s*50\b[^\n]*?"
    r"(?P<qualifier>[<>]|>=|<=)?\s*"
    r"(?P<value>\d[\d,]*(?:\.\d+)?)\s*"
    r"(?P<unit>mg/kg|g/kg)[^\n]*)",
    re.I,
)
_LC50_INH_LINE_RE = re.compile(
    r"(?P<line>[^\n]*\bLC\s*50\b[^\n]*?"
    r"(?P<qualifier>[<>]|>=|<=)?\s*"
    r"(?P<value>\d[\d,]*(?:\.\d+)?)\s*"
    r"(?P<unit>ppm|mg/m3|mg/m³|g/m3|g/m³|mg/L)[^\n]*)",
    re.I,
)

# Aquatic patterns - keep all hits with species (fix bug 5)
# Fix #3: Added ppm unit
_AQUATIC_RE = re.compile(
    r"\b(?P<endpoint>LC\s*50|EC\s*50|NOEC)\b[^\n]{0,200}?"
    r"(?P<qualifier>[<>]|>=|<=)?\s*"
    r"(?P<value>\d[\d,]*(?:\.\d+)?)\s*"
    r"(?P<unit>mg/L|mg/l|µg/L|ug/L|ppm)",
    re.I,
)
_DURATION_RE = re.compile(r"\b(?P<dur>\d+(?:\.\d+)?)\s*(?P<unit>h|hr|hrs|hour|hours|d|day|days)\b", re.I)
_SPECIES_RE = re.compile(r"\b(fish|trout|daphnia|magna|algae|aquatic|rainbow|oncorhynchus)\b", re.I)

# NOEC specific pattern (fix bug 6)
_NOEC_RE = re.compile(
    r"\bNOEC\b[^\n]{0,150}?(?P<value>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>mg/L|mg/l)",
    re.I,
)

# pH pattern for section 9 (fix bug 6)
_PH_RE = re.compile(r"\bpH[:\s]*(?P<value>\d+(?:\.\d+)?)", re.I)

# Odor pattern for section 9
_ODOR_RE = re.compile(r"Odor[:\s]*(?P<desc>[^\n]{3,100})", re.I)

# Boiling point pattern - specific extraction (fix #9)
_BOILING_POINT_RE = re.compile(
    r"Boiling\s*point[/\s]*(?:range)?\s*[:=]?\s*"
    r"(?P<qualifier>[<>~])?\s*"
    r"(?P<value>-?\d+(?:[.,]\d+)?)\s*"
    r"(?P<unit>°?\s*[CF]|deg\s*[CF]|Celsius|Fahrenheit)?\b",
    re.IGNORECASE,
)

_BCF_RE = re.compile(
    r"\b(?:BCF|bioconcentration\s*factor|bioaccumulation\s*factor)\b[^\n]{0,60}?"
    r"(\d[\d,]*(?:\.\d+)?)",
    re.I,
)
_LOGKOW_RE = re.compile(
    r"\b(?:log\s*K?\s*ow|log\s*P(?:ow)?|octanol[^\n]{0,20}partition)\b[^\n]{0,40}?"
    r"(-?\d+(?:\.\d+)?)",
    re.I,
)

# Flash point and vapor pressure patterns - from sds_regex_extractor.py
_FLASH_POINT_RE = re.compile(
    r"Flash\s*point\s*[:=]?\s*"
    r"(?P<operator>[<>~])?\s*"
    r"(?P<value>-?\d+(?:[.,]\d+)?)\s*"
    r"(?P<unit>°?\s*[CF]|deg\s*[CF]|Celsius|Fahrenheit)\b",
    re.IGNORECASE,
)

_VAPOR_PRESSURE_RE = re.compile(
    r"Vapor\s*pressure\s*[:=]?\s*"
    r"(?P<operator>[<>~])?\s*"
    r"(?P<value>\d+(?:[.,]\d+)?)\s*"
    r"(?P<unit>mmHg|mm\s*Hg|kPa|hPa|Pa|mbar|bar|Torr|atm)\b"
    r"(?:[^\n]{0,40}?\bat\s*(?P<temp>\d+(?:[.,]\d+)?)\s*(?P<tempunit>°?\s*[CF]|deg\s*[CF])\b)?",
    re.IGNORECASE,
)

# Predicted/estimated markers for section 12 (fix bug 8)
_PREDICTED_MARKERS = re.compile(r"\b(?:estimated|calculated|QSAR|ECOSAR|read-across|model|predicted)\b", re.I)


def _clip(text: str | None, n: int = 2000) -> str | None:
    """Clip text to max length."""
    if not text:
        return None
    s = " ".join(text.split())
    return s[:n] if s else None


def _first_num(pattern: str, text: str) -> str | None:
    """Extract first numeric match from pattern."""
    m = re.search(pattern, text, re.I)
    return m.group(1).strip() if m else None


def _section_after_label(text: str, label: str) -> str | None:
    """
    Extract value after a label.
    
    Fix bug 3: Parse same line first (Label: value), not next line.
    Fix #9: Ensure we get the actual value, not part of the label.
    """
    if not text:
        return None
    
    same_line = re.search(
        rf"\b{re.escape(label)}\b\s*[:\-]\s*([^\n]{{3,400}})",
        text, re.I
    )
    if same_line:
        val = same_line.group(1).strip()
        if val and not val.lower().startswith("and "):
            return val
    
    next_line = re.search(
        rf"\b{re.escape(label)}\b[^\n]{{0,40}}\n([^\n]{{8,400}})",
        text, re.I
    )
    if next_line:
        val = next_line.group(1).strip()
        if val and not val.lower().startswith("and "):
            return val
    
    return None


def _extract_pictograms(text: str) -> list[str]:
    """Extract GHS pictogram names from text."""
    names = []
    for label in (
        "Flame",
        "Exclamation",
        "Corrosion",
        "Skull",
        "Health hazard",
        "Environment",
        "Exploding",
        "Gas cylinder",
        "Oxidizer",
    ):
        if re.search(label, text, re.I):
            names.append(label)
    return names


def _kv_block(text: str, keys: tuple[str, ...]) -> dict[str, str | None]:
    """Extract key-value pairs from text block."""
    out: dict[str, str | None] = {}
    for key in keys:
        pat = rf"{key}\s*[:\-]\s*([^\n]{{3,200}})"
        m = re.search(pat, text, re.I)
        out[key] = m.group(1).strip() if m else _clip(_section_after_label(text, key), 400)
    return out


def _tox_numbers(sec11: str) -> dict[str, Any]:
    """
    Extract oral/dermal LD50 and inhalation LC50 numbers from §11.
    
    Fix bug 1: Classify route using the matched line only, not context window.
    Fix #3: Convert g/kg to mg/kg, g/m³ to mg/m³.
    Fix #8: Capture qualifiers.
    Minor: Prefer rat over mouse for oral LD50.
    """
    oral = dermal = inhalation = None
    oral_unit = dermal_unit = inh_unit = None
    oral_line = dermal_line = inh_line = None
    oral_qual = dermal_qual = inh_qual = None
    oral_is_rat = False
    
    for m in _LD50_LINE_RE.finditer(sec11 or ""):
        line = m.group("line").lower()
        val = m.group("value").replace(",", "")
        unit = m.group("unit")
        qualifier = m.group("qualifier") or ""
        try:
            num = float(val)
        except ValueError:
            continue
        
        if unit.lower() == "g/kg":
            num = num * 1000
            unit = "mg/kg"
        
        is_rat = "rat" in line
        is_mouse = "mouse" in line
        
        if "dermal" in line or "skin" in line:
            if dermal is None:
                dermal, dermal_unit = num, unit
                dermal_line = m.group("line")
                dermal_qual = qualifier
        elif "oral" in line or (is_rat and "dermal" not in line):
            if oral is None or (is_rat and not oral_is_rat and is_mouse):
                oral, oral_unit = num, unit
                oral_line = m.group("line")
                oral_qual = qualifier
                oral_is_rat = is_rat
    
    for m in _LC50_INH_LINE_RE.finditer(sec11 or ""):
        line = m.group("line").lower()
        if "fish" in line or "daphnia" in line or "algae" in line or "aquatic" in line:
            continue
        val = m.group("value").replace(",", "")
        unit = m.group("unit")
        qualifier = m.group("qualifier") or ""
        try:
            inhalation = float(val)
            if unit.lower() in ("g/m3", "g/m³"):
                inhalation = inhalation * 1000
                unit = "mg/m³"
            inh_unit = unit
            inh_line = m.group("line")
            inh_qual = qualifier
            break
        except ValueError:
            continue
    
    return {
        "ld50_oral": oral,
        "ld50_oral_unit": oral_unit,
        "ld50_oral_line": oral_line,
        "ld50_oral_qualifier": oral_qual,
        "ld50_dermal": dermal,
        "ld50_dermal_unit": dermal_unit,
        "ld50_dermal_line": dermal_line,
        "ld50_dermal_qualifier": dermal_qual,
        "lc50_inhalation": inhalation,
        "lc50_inhalation_unit": inh_unit,
        "lc50_inhalation_line": inh_line,
        "lc50_inhalation_qualifier": inh_qual,
    }


def _infer_aquatic_species(text: str) -> str | None:
    """
    Infer aquatic species from text.
    
    Priority order matters: check more specific species before generic aquatic.
    Also check the first line specially to avoid cross-line contamination.
    """
    first_line = text.split("\n")[0].lower() if "\n" in text else text.lower()
    full_text = text.lower()
    
    if "fish" in first_line or "trout" in first_line or "oncorhynchus" in first_line or "rainbow" in first_line:
        return "Fish"
    if "daphnia" in first_line or "magna" in first_line:
        return "Daphnia"
    if "algae" in first_line:
        return "Algae"
    
    if "fish" in full_text or "trout" in full_text or "oncorhynchus" in full_text or "rainbow" in full_text:
        return "Fish"
    if "daphnia" in full_text or "magna" in full_text:
        return "Daphnia"
    if "algae" in full_text:
        return "Algae"
    if "aquatic" in full_text:
        return "Aquatic"
    return None


def _eco_fields(sec12: str) -> dict[str, Any]:
    """
    Extract aquatic / persistence / biodegradation / BCF from §12.
    
    Fix bug 5: Keep all aquatic hits with species, duration, endpoint.
    Fix bug 6: Add NOEC parsing.
    Fix bug 8: Mark estimated/QSAR values as predicted.
    """
    aquatic_hits: list[dict[str, Any]] = []
    
    for m in _AQUATIC_RE.finditer(sec12 or ""):
        endpoint = m.group("endpoint").upper().replace(" ", "")
        val_str = m.group("value").replace(",", "")
        unit = m.group("unit")
        
        try:
            value = float(val_str)
        except ValueError:
            continue
        
        start = max(0, m.start() - 50)
        end = min(len(sec12 or ""), m.end() + 100)
        context = (sec12 or "")[start:end]
        
        species = _infer_aquatic_species(context)
        
        duration = None
        dur_m = _DURATION_RE.search(context)
        if dur_m:
            duration = f"{dur_m.group('dur')} {dur_m.group('unit')}"
        
        predicted = bool(_PREDICTED_MARKERS.search(context))
        
        aquatic_hits.append({
            "endpoint": endpoint,
            "value": value,
            "unit": unit,
            "species": species,
            "duration": duration,
            "predicted": predicted,
            "raw": context.strip()[:200],
        })
    
    noec_hits: list[dict[str, Any]] = []
    for m in _NOEC_RE.finditer(sec12 or ""):
        val_str = m.group("value").replace(",", "")
        unit = m.group("unit")
        try:
            value = float(val_str)
        except ValueError:
            continue
        
        start = max(0, m.start() - 50)
        end = min(len(sec12 or ""), m.end() + 100)
        context = (sec12 or "")[start:end]
        
        species = _infer_aquatic_species(context)
        duration = None
        dur_m = _DURATION_RE.search(context)
        if dur_m:
            duration = f"{dur_m.group('dur')} {dur_m.group('unit')}"
        
        predicted = bool(_PREDICTED_MARKERS.search(context))
        
        noec_hits.append({
            "endpoint": "NOEC",
            "value": value,
            "unit": unit,
            "species": species,
            "duration": duration,
            "predicted": predicted,
            "raw": context.strip()[:200],
        })
    
    bcf = None
    bm = _BCF_RE.search(sec12 or "")
    if bm:
        try:
            bcf = float(bm.group(1).replace(",", ""))
        except ValueError:
            bcf = None
    
    logkow = None
    km = _LOGKOW_RE.search(sec12 or "")
    if km:
        try:
            logkow = float(km.group(1))
        except ValueError:
            logkow = None
    
    biodeg = _clip(
        _section_after_label(sec12, "Biodegradation")
        or _section_after_label(sec12, "Persistence and degradability")
        or _section_after_label(sec12, "Ready biodegradability"),
        500,
    )
    persistence = _clip(
        _section_after_label(sec12, "Persistence")
        or _section_after_label(sec12, "Persistence and degradability"),
        500,
    )
    bioaccum = _clip(
        _section_after_label(sec12, "Bioaccumul")
        or _section_after_label(sec12, "Bioaccumulation")
        or _section_after_label(sec12, "Bioconcentration"),
        500,
    )
    
    phrase_cues: list[str] = []
    blob = (sec12 or "").lower()
    if re.search(r"not\s+consider(?:ed)?\s+harmful\s+to\s+aquatic|not\s+harmful\s+to\s+aquatic", blob):
        phrase_cues.append("Not considered harmful to aquatic life")
    
    if re.search(r"not\s+readily\s+biodegrad|not\s+inherently\s+biodegrad", blob):
        phrase_cues.append("Not readily biodegradable")
    elif re.search(r"readily\s+biodegrad|inherently\s+biodegrad", blob):
        phrase_cues.append("Readily degradable")
    elif re.search(r"\bbiodegrad", blob) and not re.search(r"not\s+biodegrad", blob):
        phrase_cues.append("Biodegradable")
    
    if re.search(r"will\s+not\s+bioaccumul|not\s+(?:likely|expected)\s+to\s+bioaccumul", blob):
        phrase_cues.append("Will not bioaccumulate")
    if re.search(r"not\s+persistent|not\s+expected\s+to\s+be\s+persistent", blob):
        phrase_cues.append("Not persistent")
    
    return {
        "aquatic_toxicity": aquatic_hits,
        "noec_hits": noec_hits,
        "persistence": persistence,
        "biodegradation": biodeg,
        "bioaccumulation": bioaccum,
        "bcf": bcf,
        "log_kow": logkow,
        "phrase_cues": phrase_cues,
        "raw_clip": _clip(sec12, 1200),
    }


def _extract_flash_points(text: str) -> list[dict[str, Any]]:
    """Extract flash point values with F→C conversion."""
    out: list[dict[str, Any]] = []
    for m in _FLASH_POINT_RE.finditer(text or ""):
        op = (m.group("operator") or "").strip()
        val_str = (m.group("value") or "").replace(",", ".")
        unit_raw = (m.group("unit") or "").replace(" ", "").lower()
        
        try:
            val = float(val_str)
        except ValueError:
            continue
        
        unit_n = unit_raw.replace("°", "")
        if unit_n.endswith("f") or "fahrenheit" in unit_n:
            value_c = (val - 32.0) * 5.0 / 9.0
            unit = "°F"
        else:
            value_c = val
            unit = "°C"
        
        out.append({
            "value_c": round(value_c, 1),
            "value": val,
            "unit": unit,
            "operator": op,
            "raw_text": m.group(0).strip(),
        })
    return out


def _extract_vapor_pressures(text: str) -> list[dict[str, Any]]:
    """Extract vapor pressure with unit conversion to mmHg."""
    out: list[dict[str, Any]] = []
    for m in _VAPOR_PRESSURE_RE.finditer(text or ""):
        val_str = (m.group("value") or "").replace(",", ".")
        unit = (m.group("unit") or "").strip().lower()
        
        try:
            val = float(val_str)
        except ValueError:
            continue
        
        if "hpa" in unit or "mbar" in unit:
            mmhg = val * 0.750062
        elif "kpa" in unit:
            mmhg = val * 7.50062
        elif "pa" in unit and "kpa" not in unit and "hpa" not in unit:
            mmhg = val * 0.00750062
        elif "bar" in unit and "mbar" not in unit:
            mmhg = val * 750.062
        elif "atm" in unit:
            mmhg = val * 760
        elif "torr" in unit or "mmhg" in unit or "mm" in unit:
            mmhg = val
        else:
            mmhg = val
        
        temp_c: float | None = None
        temp_raw = (m.group("temp") or "").strip()
        tempunit_raw = (m.group("tempunit") or "").replace(" ", "").lower()
        if temp_raw and tempunit_raw:
            try:
                temp_val = float(temp_raw.replace(",", "."))
                if "f" in tempunit_raw or "fahrenheit" in tempunit_raw:
                    temp_c = (temp_val - 32.0) * 5.0 / 9.0
                else:
                    temp_c = temp_val
            except ValueError:
                pass
        
        if mmhg >= 1:
            mmhg_rounded = round(mmhg, 2)
        elif mmhg >= 0.01:
            mmhg_rounded = round(mmhg, 4)
        else:
            mmhg_rounded = float(f"{mmhg:.3g}")
        
        out.append({
            "value": val,
            "value_mmhg": mmhg_rounded,
            "unit": m.group("unit") or "",
            "temperature_c": temp_c,
            "raw_text": m.group(0).strip(),
        })
    return out


def parse_structured_sds(sections: dict[int, str], *, full_text: str = "") -> dict[str, Any]:
    """
    Extract GHS / PPE / physchem / tox / eco / transport blocks from SDS sections.
    
    Args:
        sections: Dict mapping section numbers to section text
        full_text: Complete SDS text as fallback for NFPA search
    
    Returns:
        Structured dict with section data
    """
    sec2 = sections.get(2) or ""
    sec5 = sections.get(5) or ""
    sec7 = sections.get(7) or ""
    sec8 = sections.get(8) or ""
    sec9 = sections.get(9) or ""
    sec10 = sections.get(10) or ""
    sec11 = sections.get(11) or ""
    sec12 = sections.get(12) or ""
    sec14 = sections.get(14) or ""
    sec15 = sections.get(15) or ""
    blob = full_text or "\n".join(sections.get(i, "") for i in range(1, 17))
    
    signal = None
    sm = re.search(r"\b(Danger|Warning)\b", sec2, re.I)
    if sm:
        signal = sm.group(1).capitalize()
    
    nfpa_h = nfpa_f = nfpa_i = nfpa_s = None
    hm = _NFPA_HEALTH_RE.search(blob)
    if hm:
        nfpa_h = int(hm.group(1))
    fm = _NFPA_FIRE_RE.search(blob)
    if fm:
        nfpa_f = int(fm.group(1))
    im = _NFPA_INSTAB_RE.search(blob)
    if im:
        nfpa_i = int(im.group(1))
    sm_nfpa = _NFPA_SPECIAL_RE.search(blob)
    if sm_nfpa:
        nfpa_s = sm_nfpa.group(1)
    
    limits: list[dict[str, str]] = []
    for m in _LIMIT_LINE.finditer(sec8 or blob):
        limits.append({
            "label": m.group("label").upper().replace("  ", " "),
            "value": m.group("val"),
            "unit": m.group("unit"),
        })
    
    phys = _kv_block(
        sec9,
        (
            "Physical state",
            "Form",
            "Appearance",
            "Flash point",
            "Boiling point",
            "Melting point",
            "Vapor pressure",
            "Density",
            "Viscosity",
            "Water solubility",
            "Relative density",
            "Autoignition",
            "Explosive limits",
        ),
    )
    physical_state = (
        phys.pop("Physical state", None)
        or phys.pop("Form", None)
        or phys.pop("Appearance", None)
    )
    if not physical_state:
        m_state = re.search(
            r"(?:Physical\s*state|Form|Appearance)\s*[:\-]\s*([^\n]{2,80})",
            sec9, re.I,
        )
        if m_state:
            physical_state = m_state.group(1).strip()
    
    flash_points = _extract_flash_points(sec9)
    vapor_pressures = _extract_vapor_pressures(sec9)
    
    boiling_point_value = None
    bp_m = _BOILING_POINT_RE.search(sec9)
    if bp_m:
        bp_val = bp_m.group("value").replace(",", ".")
        bp_unit = (bp_m.group("unit") or "°C").replace(" ", "").replace("deg", "°")
        boiling_point_value = f"{bp_val} {bp_unit}"
    
    ph_value = None
    ph_m = _PH_RE.search(sec9)
    if ph_m:
        try:
            ph_value = float(ph_m.group("value"))
        except ValueError:
            pass
    
    odor = None
    odor_m = _ODOR_RE.search(sec9)
    if odor_m:
        odor = odor_m.group("desc").strip()
    
    tox_nums = _tox_numbers(sec11)
    eco = _eco_fields(sec12)
    
    combustion_cues: list[str] = []
    fire_blob = f"{sec5}\n{sec10}".lower()
    if re.search(r"form\s+(?:sox|nox|so2|no2)|may\s+form\s+(?:sulfur|nitrogen)\s+oxide", fire_blob):
        combustion_cues.append("Product may form SOx or NOx upon combustion")
    elif re.search(r"\b(?:sox|nox|so2|no2)\b", fire_blob):
        combustion_cues.append("Product may form SOx or NOx upon combustion")
    
    return {
        "section_2": {
            "signal_word": signal,
            "ghs_classes": _clip(sec2, 800),
            "h_statements": sorted({c.upper() for c in _H_RE.findall(sec2)}),
            "p_statements": sorted({c.upper() for c in _P_RE.findall(sec2)}),
            "pictograms": _extract_pictograms(sec2),
        },
        "section_5": {
            "firefighting": _clip(sec5, 800),
            "hazardous_combustion": _clip(
                _section_after_label(sec5, "Hazardous combustion")
                or _section_after_label(sec5, "Combustion product"),
                500,
            ),
            "combustion_phrase_cues": combustion_cues,
        },
        "section_7": {
            "storage": _clip(_section_after_label(sec7, "Storage"), 800),
            "handling": _clip(_section_after_label(sec7, "Handling"), 800),
        },
        "section_8": {
            "gloves": _clip(
                _section_after_label(sec8, "Glove") or _section_after_label(sec8, "Hand protection"),
                500,
            ),
            "ppe": _clip(
                _section_after_label(sec8, "Personal protective") or _section_after_label(sec8, "PPE"),
                800,
            ),
            "respiratory_protection": _clip(_section_after_label(sec8, "Respiratory"), 500),
            "eye_protection": _clip(_section_after_label(sec8, "Eye"), 400),
            "skin_protection": _clip(
                _section_after_label(sec8, "Skin") or _section_after_label(sec8, "Body"), 400
            ),
            "engineering_controls": _clip(_section_after_label(sec8, "Engineering"), 500),
            "exposure_limits": limits,
            "osha_pel": next((x for x in limits if "OSHA" in x["label"] and "PEL" in x["label"]), None),
            "niosh_rel": next((x for x in limits if "NIOSH" in x["label"]), None),
            "tlv": next((x for x in limits if x["label"] in ("TLV", "TWA") or "TLV" in x["label"]), None),
            "stel": next((x for x in limits if "STEL" in x["label"]), None),
            "ceiling": next((x for x in limits if "CEILING" in x["label"]), None),
            "idlh": next((x for x in limits if "IDLH" in x["label"]), None),
        },
        "section_9": {
            "physical_state": physical_state,
            "form": physical_state,
            "flash_point": phys.get("Flash point") or (
                f"{flash_points[0]['value_c']} °C" if flash_points else None
            ),
            "flash_points": flash_points,
            "boiling_point": boiling_point_value or phys.get("Boiling point"),
            "melting_point": phys.get("Melting point"),
            "vapor_pressure": phys.get("Vapor pressure") or (
                f"{vapor_pressures[0]['value_mmhg']} mmHg" if vapor_pressures else None
            ),
            "vapor_pressures": vapor_pressures,
            "density": phys.get("Density"),
            "viscosity": phys.get("Viscosity"),
            "water_solubility": phys.get("Water solubility"),
            "relative_density": phys.get("Relative density"),
            "autoignition": phys.get("Autoignition"),
            "explosive_limits": phys.get("Explosive limits"),
            "ph": ph_value,
            "odor": odor,
        },
        "section_10": {
            "incompatible_materials": _clip(_section_after_label(sec10, "Incompatible"), 600),
            "hazardous_decomposition": _clip(_section_after_label(sec10, "Hazardous decomposition"), 600),
            "reactivity": _clip(_section_after_label(sec10, "Reactivity"), 400),
            "combustion_phrase_cues": combustion_cues,
        },
        "section_11": {
            "acute_toxicity": _clip(_section_after_label(sec11, "Acute"), 800),
            "sensitization": _clip(_section_after_label(sec11, "Sensitiz"), 400),
            "carcinogenicity": _clip(_section_after_label(sec11, "Carcino"), 400),
            "reproductive_toxicity": _clip(_section_after_label(sec11, "Reproduct"), 400),
            "stot": _clip(
                _section_after_label(sec11, "STOT") or _section_after_label(sec11, "specific target"),
                400,
            ),
            "aspiration_hazard": _clip(_section_after_label(sec11, "Aspiration"), 300),
            **tox_nums,
        },
        "section_12": eco,
        "section_14": {
            "un_number": (m.group(1) if (m := _UN_RE.search(sec14)) else None),
            "dot_class": _clip(_section_after_label(sec14, "Class"), 200),
            "packing_group": _first_num(r"Packing\s*(?:Group|group)\s*[:\-]?\s*(I{1,3}|IV|1|2|3|II)", sec14),
        },
        "section_15": {
            "regulatory_information": _clip(sec15, 1500),
        },
        "nfpa_health": nfpa_h,
        "nfpa_fire": nfpa_f,
        "nfpa_instability": nfpa_i,
        "nfpa_special": nfpa_s,
        "physical_state": physical_state,
    }
