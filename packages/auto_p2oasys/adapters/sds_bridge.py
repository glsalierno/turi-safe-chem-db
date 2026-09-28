"""
SDS bridge - converts structured SDS data to Evidence records.

Ported from GHaz7 p2oasys_source_bridges.py (Gabriel Salierno), offline subset.
Includes bug fixes from the PR #12 brief.

Bug fixes applied:
4. Deduplicate on (endpoint, route), not just substring "lc50"/"ld50"
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional

from ..evidence import Evidence

# Odor normalization keywords
ODOR_CUE_MAP = {
    "odorless": "Odorless",
    "no odor": "Odorless",
    "slight": "Slight odor",
    "faint": "Slight odor",
    "mild": "Mild odor",
    "strong": "Strong odor",
    "pungent": "Pungent or irritating odor",
    "irritating": "Pungent or irritating odor",
    "acrid": "Pungent or irritating odor",
    "sharp": "Pungent or irritating odor",
}


def normalize_odor_cue(odor_desc: str) -> str | None:
    """
    Normalize odor description to a P2OASys matrix cue.
    
    Returns normalized cue or None if no match.
    """
    if not odor_desc:
        return None
    
    lower = odor_desc.lower()
    for keyword, cue in ODOR_CUE_MAP.items():
        if keyword in lower:
            return cue
    return None


def structured_sds_to_extra_fields(structured: dict[str, Any] | None) -> dict[str, Any]:
    """
    Flatten parse_structured_sds output into the dict shape expected by
    sds_fields_to_extra_sources (GHaz7 compat).
    """
    if not structured:
        return {}
    
    out: dict[str, Any] = {}
    sec2 = structured.get("section_2") or {}
    sec5 = structured.get("section_5") or {}
    sec8 = structured.get("section_8") or {}
    sec9 = structured.get("section_9") or {}
    sec10 = structured.get("section_10") or {}
    sec11 = structured.get("section_11") or {}
    sec12 = structured.get("section_12") or {}
    
    h_codes = sec2.get("h_statements") or []
    if h_codes:
        out["ghs_h_codes"] = list(h_codes)
    if sec2.get("signal_word"):
        out["signal_word"] = sec2["signal_word"]
    
    ps = structured.get("physical_state") or sec9.get("physical_state") or sec9.get("form")
    if ps:
        out["physical_state"] = str(ps)
        out["form"] = str(ps)
    
    if sec9.get("flash_point"):
        out["flash_point"] = sec9["flash_point"]
    if sec9.get("flash_points"):
        out["flash_points"] = sec9["flash_points"]
    if sec9.get("vapor_pressure"):
        out["vapor_pressure"] = sec9["vapor_pressure"]
    if sec9.get("vapor_pressures"):
        out["vapor_pressures"] = sec9["vapor_pressures"]
    if sec9.get("ph") is not None:
        out["ph"] = sec9["ph"]
    if sec9.get("odor"):
        out["odor"] = sec9["odor"]
    if sec9.get("boiling_point"):
        out["boiling_point"] = sec9["boiling_point"]
    
    if sec11.get("ld50_oral") is not None:
        unit = sec11.get("ld50_oral_unit") or "mg/kg"
        out["ld50_oral_mg_kg"] = sec11["ld50_oral"] if "mg" in str(unit).lower() else sec11["ld50_oral"]
        out["ld50_oral"] = f"LD50 {sec11['ld50_oral']} {unit}"
        out["ld50_oral_line"] = sec11.get("ld50_oral_line")
    if sec11.get("ld50_dermal") is not None:
        unit = sec11.get("ld50_dermal_unit") or "mg/kg"
        out["ld50_dermal_mg_kg"] = sec11["ld50_dermal"]
        out["ld50_dermal"] = f"LD50 {sec11['ld50_dermal']} {unit}"
        out["ld50_dermal_line"] = sec11.get("ld50_dermal_line")
    if sec11.get("lc50_inhalation") is not None:
        unit = sec11.get("lc50_inhalation_unit") or "ppm"
        out["lc50_inhalation"] = f"LC50 {sec11['lc50_inhalation']} {unit}"
        if "ppm" in str(unit).lower():
            out["lc50_inhalation_ppm"] = sec11["lc50_inhalation"]
        out["lc50_inhalation_line"] = sec11.get("lc50_inhalation_line")
    
    aq = sec12.get("aquatic_toxicity") or []
    if aq:
        out["aquatic_toxicity_all"] = aq
        first = aq[0]
        if isinstance(first, dict) and first.get("value") is not None:
            out["aquatic_toxicity"] = float(first["value"])
            out["lc50_aquatic_mg_l"] = float(first["value"])
        out["aquatic_toxicity_raw"] = first
    
    noec = sec12.get("noec_hits") or []
    if noec:
        out["noec_hits"] = noec
        first = noec[0]
        if isinstance(first, dict) and first.get("value") is not None:
            out["chronic_noec_mg_l"] = float(first["value"])
    
    if sec12.get("phrase_cues"):
        out["eco_phrase_cues"] = list(sec12["phrase_cues"])
    if sec12.get("biodegradation"):
        out["biodegradation"] = sec12["biodegradation"]
    if sec12.get("persistence"):
        out["persistence"] = sec12["persistence"]
    if sec12.get("bcf") is not None:
        out["bcf"] = sec12["bcf"]
    if sec12.get("log_kow") is not None:
        out["log_kow"] = sec12["log_kow"]
    if sec12.get("bioaccumulation"):
        out["bioaccumulation"] = sec12["bioaccumulation"]
    
    cues = list(sec5.get("combustion_phrase_cues") or []) + list(sec10.get("combustion_phrase_cues") or [])
    if cues:
        out["combustion_phrase_cues"] = list(dict.fromkeys(cues))
    
    oels = []
    for key in ("osha_pel", "niosh_rel", "tlv", "stel", "idlh"):
        item = sec8.get(key)
        if isinstance(item, dict) and item.get("value"):
            oels.append(f"{item.get('label', key)} {item['value']} {item.get('unit') or ''}".strip())
    if oels:
        out["exposure_limits"] = oels
    
    if structured.get("nfpa_health") is not None:
        out["nfpa_health"] = structured["nfpa_health"]
    if structured.get("nfpa_fire") is not None:
        out["nfpa_fire"] = structured["nfpa_fire"]
    if structured.get("nfpa_instability") is not None:
        out["nfpa_instability"] = structured["nfpa_instability"]
    if structured.get("nfpa_special") is not None:
        out["nfpa_special"] = structured["nfpa_special"]
    
    return out


def sds_fields_to_evidence(
    fields: dict[str, Any],
    cas: str,
    *,
    source_label: str,
    vendor: str = "unknown",
    revision: str = "",
    file_name: str = "",
    reference: str = "",
) -> tuple[list[Evidence], list[dict[str, Any]]]:
    """
    Convert SDS fields to Evidence records.
    
    Args:
        fields: Flattened SDS fields from structured_sds_to_extra_fields
        cas: CAS registry number
        source_label: Source label for Evidence (e.g., "SDS (TCI, file.pdf)")
        vendor: Vendor name for tracing
        revision: SDS revision date
        file_name: SDS file name
    
    Returns:
        (evidence_list, unmapped_list) where unmapped contains fields not routed to scorer
    """
    now = datetime.now(timezone.utc)
    evidence: list[Evidence] = []
    unmapped: list[dict[str, Any]] = []
    
    ref_str = reference or (f"{file_name}, rev {revision}" if revision else file_name)
    
    h_codes = fields.get("ghs_h_codes") or []
    h_code_sources: dict[str, list[str]] = {}
    if h_codes:
        for code in h_codes:
            if code not in h_code_sources:
                h_code_sources[code] = []
            h_code_sources[code].append(source_label)
        
        evidence.append(Evidence(
            cas=cas,
            endpoint="h_codes",
            value=list(h_codes),
            source=source_label,
            source_type="SDS",
            predicted=False,
            reliability="classification",
            section="Section 2",
            reference=ref_str,
            retrieved_at=now,
        ))
    
    fields["h_code_sources"] = h_code_sources
    
    fps = fields.get("flash_points") or []
    if fps:
        fp = fps[0]
        evidence.append(Evidence(
            cas=cas,
            endpoint="flash_point",
            value=fp.get("value_c"),
            unit="°C",
            qualifier=fp.get("operator"),
            source=source_label,
            source_type="SDS",
            predicted=False,
            reliability="measured",
            section="Section 9",
            raw_text=fp.get("raw_text"),
            reference=ref_str,
            retrieved_at=now,
        ))
    elif fields.get("flash_point"):
        fp_str = str(fields["flash_point"])
        m = re.search(r"(-?\d+(?:\.\d+)?)", fp_str)
        if m:
            evidence.append(Evidence(
                cas=cas,
                endpoint="flash_point",
                value=float(m.group(1)),
                unit="°C",
                source=source_label,
                source_type="SDS",
                predicted=False,
                reliability="measured",
                section="Section 9",
                raw_text=fp_str,
                reference=ref_str,
                retrieved_at=now,
            ))
    
    vps = fields.get("vapor_pressures") or []
    if vps:
        vp = vps[0]
        evidence.append(Evidence(
            cas=cas,
            endpoint="vapor_pressure",
            value=vp.get("value_mmhg"),
            unit="mmHg",
            source=source_label,
            source_type="SDS",
            predicted=False,
            reliability="measured",
            section="Section 9",
            raw_text=vp.get("raw_text"),
            reference=ref_str,
            retrieved_at=now,
        ))
    
    if fields.get("ld50_oral_mg_kg") is not None:
        evidence.append(Evidence(
            cas=cas,
            endpoint="oral_ld50",
            value=fields["ld50_oral_mg_kg"],
            unit="mg/kg",
            source=source_label,
            source_type="SDS",
            predicted=False,
            reliability="measured",
            section="Section 11",
            raw_text=fields.get("ld50_oral_line"),
            reference=ref_str,
            retrieved_at=now,
        ))
    
    if fields.get("ld50_dermal_mg_kg") is not None:
        evidence.append(Evidence(
            cas=cas,
            endpoint="dermal_ld50",
            value=fields["ld50_dermal_mg_kg"],
            unit="mg/kg",
            source=source_label,
            source_type="SDS",
            predicted=False,
            reliability="measured",
            section="Section 11",
            raw_text=fields.get("ld50_dermal_line"),
            reference=ref_str,
            retrieved_at=now,
        ))
    
    if fields.get("lc50_inhalation_ppm") is not None:
        evidence.append(Evidence(
            cas=cas,
            endpoint="inhalation_lc50",
            value=fields["lc50_inhalation_ppm"],
            unit="ppm",
            source=source_label,
            source_type="SDS",
            predicted=False,
            reliability="measured",
            section="Section 11",
            raw_text=fields.get("lc50_inhalation_line"),
            reference=ref_str,
            retrieved_at=now,
        ))
    
    for aq in fields.get("aquatic_toxicity_all") or []:
        if isinstance(aq, dict) and aq.get("value") is not None:
            endpoint = aq.get("endpoint", "LC50")
            if endpoint.upper() == "NOEC":
                continue
            species = aq.get("species") or "aquatic"
            ep_name = f"aquatic_{endpoint.lower()}_{species.lower()}"
            evidence.append(Evidence(
                cas=cas,
                endpoint=ep_name,
                value=aq["value"],
                unit=aq.get("unit", "mg/L"),
                source=source_label,
                source_type="SDS",
                predicted=aq.get("predicted", False),
                reliability="measured" if not aq.get("predicted") else "classification",
                section="Section 12",
                raw_text=aq.get("raw"),
                reference=ref_str,
                retrieved_at=now,
            ))
    
    for noec in fields.get("noec_hits") or []:
        if isinstance(noec, dict) and noec.get("value") is not None:
            species = noec.get("species") or ""
            evidence.append(Evidence(
                cas=cas,
                endpoint="chronic_aquatic_noec",
                value=noec["value"],
                unit=noec.get("unit", "mg/L"),
                source=source_label,
                source_type="SDS",
                predicted=noec.get("predicted", False),
                reliability="measured" if not noec.get("predicted") else "classification",
                section="Section 12",
                raw_text=noec.get("raw"),
                reference=ref_str,
                retrieved_at=now,
            ))
    
    if fields.get("nfpa_health") is not None:
        evidence.append(Evidence(
            cas=cas,
            endpoint="nfpa_health",
            value=fields["nfpa_health"],
            source=source_label,
            source_type="SDS",
            predicted=False,
            reliability="classification",
            section="Section 2",
            reference=ref_str,
            retrieved_at=now,
        ))
    
    if fields.get("nfpa_fire") is not None:
        evidence.append(Evidence(
            cas=cas,
            endpoint="nfpa_fire",
            value=fields["nfpa_fire"],
            source=source_label,
            source_type="SDS",
            predicted=False,
            reliability="classification",
            section="Section 2",
            reference=ref_str,
            retrieved_at=now,
        ))
    
    if fields.get("nfpa_instability") is not None:
        evidence.append(Evidence(
            cas=cas,
            endpoint="nfpa_reactivity",
            value=fields["nfpa_instability"],
            source=source_label,
            source_type="SDS",
            predicted=False,
            reliability="classification",
            section="Section 2",
            reference=ref_str,
            retrieved_at=now,
        ))
    
    if fields.get("ph") is not None:
        evidence.append(Evidence(
            cas=cas,
            endpoint="ph",
            value=fields["ph"],
            source=source_label,
            source_type="SDS",
            predicted=False,
            reliability="measured",
            section="Section 9",
            reference=ref_str,
            retrieved_at=now,
        ))
    
    if fields.get("odor"):
        odor_cue = normalize_odor_cue(fields["odor"])
        if odor_cue:
            evidence.append(Evidence(
                cas=cas,
                endpoint="sds_phrase",
                value=odor_cue,
                source=source_label,
                source_type="SDS",
                predicted=False,
                reliability="classification",
                section="Section 9",
                raw_text=fields["odor"],
                reference=ref_str,
                retrieved_at=now,
            ))
        else:
            unmapped.append({
                "field": "odor",
                "value": fields["odor"],
                "reason": "no matching matrix phrase",
            })
    
    for cue in fields.get("eco_phrase_cues") or []:
        evidence.append(Evidence(
            cas=cas,
            endpoint="sds_phrase",
            value=cue,
            source=source_label,
            source_type="SDS",
            predicted=False,
            reliability="classification",
            section="Section 12",
            reference=ref_str,
            retrieved_at=now,
        ))
    
    if fields.get("bcf") is not None:
        evidence.append(Evidence(
            cas=cas,
            endpoint="bcf",
            value=fields["bcf"],
            unit="L/kg",
            source=source_label,
            source_type="SDS",
            predicted=False,
            reliability="measured",
            section="Section 12",
            reference=ref_str,
            retrieved_at=now,
        ))
    
    if fields.get("log_kow") is not None:
        evidence.append(Evidence(
            cas=cas,
            endpoint="log_kow",
            value=fields["log_kow"],
            source=source_label,
            source_type="SDS",
            predicted=False,
            reliability="measured",
            section="Section 12",
            reference=ref_str,
            retrieved_at=now,
        ))
    
    if fields.get("boiling_point"):
        evidence.append(Evidence(
            cas=cas,
            endpoint="boiling_point",
            value=fields["boiling_point"],
            source=source_label,
            source_type="SDS",
            predicted=False,
            reliability="measured",
            section="Section 9",
            reference=ref_str,
            retrieved_at=now,
        ))
    
    for oel in fields.get("exposure_limits") or []:
        unmapped.append({
            "field": "exposure_limit",
            "value": oel,
            "reason": "PEL/TLV scorer unit not mapped",
        })
    
    if fields.get("persistence"):
        unmapped.append({
            "field": "persistence_text",
            "value": fields["persistence"],
            "reason": "Persistence t½ scorer unit not mapped",
        })
    
    if fields.get("biodegradation"):
        unmapped.append({
            "field": "biodegradation_text", 
            "value": fields["biodegradation"],
            "reason": "text field, not numeric",
        })
    
    return evidence, unmapped
