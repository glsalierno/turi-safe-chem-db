"""
Bridge between IUCLID extracted endpoints and P2OASys scorer.

Converts extracted endpoints to extra_sources format compatible with
hazard_for_p2oasys.merge_extra_sources.

Output format for each evidence item:
{
    "value": "LD50 4934 mg/kg bw",
    "unit": "mg/kg",
    "species_route": ["oral", "rat"],
    "source": "IUCLID",
    "predicted": False,
    "dossier_id": "uuid",
    "reliability": 2
}

Selection rules:
- Drop Klimisch 3/4 and "not assignable"
- Prefer key results
- Take most conservative value (min LD50/LC50/EC50/NOAEL, min flash point, max VP)
- Aquatic acute uses LC50/EC50 only, never EC0/EC100/NOEC
- Convert mL/kg only when density is known, else reject with reason
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


ACUTE_ORAL_SUBTYPES = {"AcuteToxicityOral"}
ACUTE_DERMAL_SUBTYPES = {"AcuteToxicityDermal"}
ACUTE_INHALATION_SUBTYPES = {"AcuteToxicityInhalation"}
REPEATED_DOSE_ORAL_SUBTYPES = {"RepeatedDoseToxicityOral"}
REPEATED_DOSE_INHALATION_SUBTYPES = {"RepeatedDoseToxicityInhalation"}
AQUATIC_SUBTYPES = {
    "ShortTermToxicityToFish",
    "LongTermToxToFish",
    "ShortTermToxicityToAquaInv",
    "LongTermToxicityToAquaInv",
    "ToxicityToAquaticAlgae",
}

VALID_AQUATIC_ENDPOINTS = {"LC50", "EC50", "IC50"}


@dataclass
class RejectedEndpoint:
    """Record of a rejected endpoint with reason."""

    subtype: str
    endpoint: str
    value: float | None
    unit: str
    reason: str
    dossier_uuid: str


@dataclass
class BridgeResult:
    """Result of bridge conversion with selected values and rejections."""

    extra_sources: dict[str, Any]
    rejected: list[RejectedEndpoint] = field(default_factory=list)


def _get_reliability_score(endpoint: dict) -> int | None:
    """Extract Klimisch score (1-4) from reliability string."""
    rel = endpoint.get("reliability", "")
    if not rel:
        return None
    for i in range(1, 5):
        if rel.startswith(str(i)):
            return i
    return None


def _is_reliable(endpoint: dict) -> bool:
    """Check if reliability is Klimisch 1 or 2."""
    score = _get_reliability_score(endpoint)
    return score is not None and score <= 2


def _get_numeric_value(endpoint: dict) -> float | None:
    """Get numeric value from endpoint."""
    val = endpoint.get("value")
    if val is None:
        return None
    if isinstance(val, dict):
        return val.get("lower") or val.get("upper")
    return None


def _get_unit(endpoint: dict) -> str:
    """Get unit from endpoint."""
    val = endpoint.get("value")
    if val is None:
        return ""
    if isinstance(val, dict):
        return val.get("unit", "")
    return ""


def _normalize_unit(unit: str) -> str:
    """Normalize unit for comparison."""
    return unit.lower().strip().replace(" ", "")


def _make_evidence(
    endpoint: dict,
    value_str: str,
    unit_normalized: str,
    species_route: list[str],
) -> dict[str, Any]:
    """Create evidence dict for P2OASys."""
    return {
        "value": value_str,
        "unit": unit_normalized,
        "species_route": species_route,
        "source": "IUCLID",
        "predicted": False,
        "dossier_id": endpoint.get("dossier_uuid", ""),
        "reliability": _get_reliability_score(endpoint),
        "document": endpoint.get("document", ""),
        "subtype": endpoint.get("subtype", ""),
        "study_result_type": endpoint.get("study_result_type", ""),
        "key_result": endpoint.get("key_result", False),
    }


def _select_min_value(
    endpoints: list[dict],
    subtypes: set[str],
    rejected: list[RejectedEndpoint],
    endpoint_filter: set[str] | None = None,
    route_filter: str | None = None,
) -> dict | None:
    """Select endpoint with minimum value from matching endpoints."""
    candidates: list[tuple[float, dict]] = []
    
    for ep in endpoints:
        if ep.get("subtype") not in subtypes:
            continue
        
        if endpoint_filter and ep.get("endpoint") not in endpoint_filter:
            rejected.append(
                RejectedEndpoint(
                    subtype=ep.get("subtype", ""),
                    endpoint=ep.get("endpoint", ""),
                    value=_get_numeric_value(ep),
                    unit=_get_unit(ep),
                    reason=f"Endpoint {ep.get('endpoint')} not in {endpoint_filter}",
                    dossier_uuid=ep.get("dossier_uuid", ""),
                )
            )
            continue
        
        if route_filter:
            route = ep.get("route", "").lower()
            if route_filter.lower() not in route:
                continue
        
        if not _is_reliable(ep):
            rejected.append(
                RejectedEndpoint(
                    subtype=ep.get("subtype", ""),
                    endpoint=ep.get("endpoint", ""),
                    value=_get_numeric_value(ep),
                    unit=_get_unit(ep),
                    reason=f"Reliability {ep.get('reliability')} not acceptable",
                    dossier_uuid=ep.get("dossier_uuid", ""),
                )
            )
            continue
        
        val = _get_numeric_value(ep)
        if val is None:
            continue
        
        unit = _get_unit(ep)
        unit_norm = _normalize_unit(unit)
        
        if "ml/kg" in unit_norm:
            rejected.append(
                RejectedEndpoint(
                    subtype=ep.get("subtype", ""),
                    endpoint=ep.get("endpoint", ""),
                    value=val,
                    unit=unit,
                    reason="mL/kg requires density conversion (not available)",
                    dossier_uuid=ep.get("dossier_uuid", ""),
                )
            )
            continue
        
        candidates.append((val, ep))
    
    if not candidates:
        return None
    
    key_results = [(v, e) for v, e in candidates if e.get("key_result")]
    if key_results:
        candidates = key_results
    
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def _select_max_value(
    endpoints: list[dict],
    subtypes: set[str],
    rejected: list[RejectedEndpoint],
) -> dict | None:
    """Select endpoint with maximum value from matching endpoints."""
    candidates: list[tuple[float, dict]] = []
    
    for ep in endpoints:
        if ep.get("subtype") not in subtypes:
            continue
        
        if not _is_reliable(ep):
            rejected.append(
                RejectedEndpoint(
                    subtype=ep.get("subtype", ""),
                    endpoint=ep.get("endpoint", ""),
                    value=_get_numeric_value(ep),
                    unit=_get_unit(ep),
                    reason=f"Reliability {ep.get('reliability')} not acceptable",
                    dossier_uuid=ep.get("dossier_uuid", ""),
                )
            )
            continue
        
        val = _get_numeric_value(ep)
        if val is None:
            continue
        
        candidates.append((val, ep))
    
    if not candidates:
        return None
    
    key_results = [(v, e) for v, e in candidates if e.get("key_result")]
    if key_results:
        candidates = key_results
    
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def _convert_vp_to_mmhg(value: float, unit: str) -> float | None:
    """Convert vapour pressure to mm Hg."""
    unit_norm = _normalize_unit(unit)
    if "mmhg" in unit_norm or "torr" in unit_norm:
        return value
    if "kpa" in unit_norm:
        return value * 7.50062
    if "pa" in unit_norm and "kpa" not in unit_norm:
        return value * 0.00750062
    if "bar" in unit_norm:
        return value * 750.062
    if "atm" in unit_norm:
        return value * 760.0
    return None


def endpoints_to_extra_sources(
    endpoints: list[dict],
    cas: str,
) -> dict[str, Any] | None:
    """
    Convert extracted endpoints to P2OASys extra_sources format.
    
    Args:
        endpoints: List of endpoint dicts from extractor
        cas: CAS number for reference
    
    Returns:
        Dict with toxicities[], hazard_metrics{}, source_info{}
        or None if no usable data
    """
    if not endpoints:
        return None
    
    rejected: list[RejectedEndpoint] = []
    toxicities: list[dict] = []
    hazard_metrics: dict[str, Any] = {}
    
    oral_ld50 = _select_min_value(
        endpoints,
        ACUTE_ORAL_SUBTYPES,
        rejected,
        endpoint_filter={"LD50"},
    )
    if oral_ld50:
        val = _get_numeric_value(oral_ld50)
        unit = _get_unit(oral_ld50)
        species = oral_ld50.get("species", "").lower() or "unspecified"
        toxicities.append(
            _make_evidence(
                oral_ld50,
                f"LD50 {val} {unit}",
                re.sub(r"\s*bw\s*$", "", unit, flags=re.I),
                ["oral", species],
            )
        )
    
    dermal_ld50 = _select_min_value(
        endpoints,
        ACUTE_DERMAL_SUBTYPES,
        rejected,
        endpoint_filter={"LD50"},
    )
    if dermal_ld50:
        val = _get_numeric_value(dermal_ld50)
        unit = _get_unit(dermal_ld50)
        species = dermal_ld50.get("species", "").lower() or "unspecified"
        toxicities.append(
            _make_evidence(
                dermal_ld50,
                f"LD50 {val} {unit}",
                re.sub(r"\s*bw\s*$", "", unit, flags=re.I),
                ["dermal", species],
            )
        )
    
    inhal_lc50 = _select_min_value(
        endpoints,
        ACUTE_INHALATION_SUBTYPES,
        rejected,
        endpoint_filter={"LC50"},
    )
    if inhal_lc50:
        val = _get_numeric_value(inhal_lc50)
        unit = _get_unit(inhal_lc50)
        species = inhal_lc50.get("species", "").lower() or "unspecified"
        toxicities.append(
            _make_evidence(
                inhal_lc50,
                f"LC50 {val} {unit}",
                unit,
                ["inhalation", species],
            )
        )
    
    oral_noael = _select_min_value(
        endpoints,
        REPEATED_DOSE_ORAL_SUBTYPES,
        rejected,
        endpoint_filter={"NOAEL", "LOAEL"},
    )
    if oral_noael:
        val = _get_numeric_value(oral_noael)
        unit = _get_unit(oral_noael)
        ep_type = oral_noael.get("endpoint", "NOAEL")
        species = oral_noael.get("species", "").lower() or "unspecified"
        toxicities.append(
            _make_evidence(
                oral_noael,
                f"{ep_type} {val} {unit}",
                unit,
                ["oral", "repeated-dose", species],
            )
        )
    
    aquatic_acute = _select_min_value(
        endpoints,
        AQUATIC_SUBTYPES,
        rejected,
        endpoint_filter=VALID_AQUATIC_ENDPOINTS,
    )
    if aquatic_acute:
        val = _get_numeric_value(aquatic_acute)
        unit = _get_unit(aquatic_acute)
        ep_type = aquatic_acute.get("endpoint", "EC50")
        species = aquatic_acute.get("species", "").lower() or "aquatic"
        
        taxon = "aquatic"
        species_lower = species.lower()
        if "fish" in species_lower or "cyprinus" in species_lower:
            taxon = "fish"
        elif "daphnia" in species_lower:
            taxon = "daphnia"
        elif "algae" in species_lower or "chlorella" in species_lower or "desmodesmus" in species_lower:
            taxon = "algae"
        elif "artemia" in species_lower:
            taxon = "invertebrate"
        
        toxicities.append(
            _make_evidence(
                aquatic_acute,
                f"{ep_type} {val} {unit}",
                unit,
                ["aquatic", taxon, species],
            )
        )
        
        unit_norm = _normalize_unit(unit)
        if "mg/l" in unit_norm:
            hazard_metrics["lc50_aquatic_mg_l"] = {
                "value": val,
                "predicted": False,
                "source": "IUCLID",
                "taxon": taxon,
                "endpoint": ep_type,
            }
    
    flash_points = [
        ep for ep in endpoints
        if ep.get("subtype") == "FlashPoint" and _is_reliable(ep)
    ]
    if flash_points:
        fp_min = _select_min_value(
            endpoints, {"FlashPoint"}, rejected
        )
        if fp_min:
            val = _get_numeric_value(fp_min)
            unit = _get_unit(fp_min)
            unit_norm = _normalize_unit(unit)
            if "°c" in unit_norm or "c" == unit_norm:
                hazard_metrics["flash_point_c"] = {
                    "value": val,
                    "predicted": False,
                    "source": "IUCLID",
                    "dossier_id": fp_min.get("dossier_uuid", ""),
                }
    
    vp_selected = _select_max_value(endpoints, {"Vapour"}, rejected)
    if vp_selected:
        val = _get_numeric_value(vp_selected)
        unit = _get_unit(vp_selected)
        mmhg = _convert_vp_to_mmhg(val, unit) if val else None
        if mmhg is not None:
            hazard_metrics["vapor_pressure_mmhg"] = {
                "value": mmhg,
                "predicted": False,
                "source": "IUCLID",
                "original_value": val,
                "original_unit": unit,
                "dossier_id": vp_selected.get("dossier_uuid", ""),
            }
    
    log_kow = _select_min_value(endpoints, {"Partition"}, rejected)
    if log_kow:
        val = _get_numeric_value(log_kow)
        type_str = log_kow.get("extras", {}).get("type", "")
        if isinstance(type_str, dict):
            type_str = ""
        if "log" in str(type_str).lower() or val is not None:
            hazard_metrics["log_kow"] = {
                "value": val,
                "predicted": False,
                "source": "IUCLID",
                "dossier_id": log_kow.get("dossier_uuid", ""),
            }
    
    if not toxicities and not hazard_metrics:
        return None
    
    return {
        "toxicities": toxicities,
        "hazard_metrics": hazard_metrics,
        "source_info": {
            "source": "ECHA REACH Study Results (IUCLID)",
            "release": "2023-05-23",
            "cas": cas,
            "endpoint_count": len(endpoints),
            "basis": "measured",
        },
        "rejected": [
            {
                "subtype": r.subtype,
                "endpoint": r.endpoint,
                "value": r.value,
                "unit": r.unit,
                "reason": r.reason,
                "dossier_uuid": r.dossier_uuid,
            }
            for r in rejected
        ],
    }
