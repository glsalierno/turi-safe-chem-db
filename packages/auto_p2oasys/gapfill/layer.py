"""
Gap-fill layer implementation.

For each of the 34 auto subcategories:
- Try pathways in order, measured before predicted
- Stop at first reliable one (P2OASys is OR-of-pathways)
- Keep other evidence in trace
- Predicted-only values labeled
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..evidence import Evidence


AUTO6_CATEGORIES = {
    "Acute Human Effects": [
        "Inhalation Toxicity",
        "Oral Toxicity",
        "Dermal Toxicity",
        "Skin Sensitization",
        "Dermal Irritation",
        "Eye Irritation",
        "Health",
        "Respiratory Sensitization",
        "Aspiration Hazard",
    ],
    "Chronic Human Effects": [
        "Carcinogen",
        "Mutagen/ Teratogen",
        "Reproductive Toxicity",
        "Other Chronic Organ Effects",
        "Neurotoxicity",
        "Endocrine Disruption",
        "Immunotoxicity",
    ],
    "Ecological Hazards": [
        "Acute Aquatic Toxicity",
        "Chronic Aquatic Toxicity (fish, crustacea or algae)",
    ],
    "Environmental Fate & Transport": [
        "Persistence",
        "Bioconcentration/ Bioaccumulation",
        "Biodegradation",
    ],
    "Atmospheric Hazard": [
        "Atmospheric Hazard",
        "Ozone Depletor",
        "NESHAP",
        "Acid Rain Precursor",
    ],
    "Physical Properties": [
        "Vapor Pressure",
        "Flammability: Liquid",
        "Flammability: Solid",
        "Flammability: Gas",
        "Explosivity",
        "Oxidizer",
        "Corrosive",
        "Reactivity",
        "pH",
    ],
}


SUBCATEGORY_PATHWAYS = {
    "Oral Toxicity": [
        ("oral_ld50", "measured"),
        ("pubchem", "measured"),
        ("sds", "measured"),
        ("toxvaldb", "measured"),
    ],
    "Inhalation Toxicity": [
        ("inhalation_lc50", "measured"),
        ("pubchem", "measured"),
        ("sds", "measured"),
    ],
    "Dermal Toxicity": [
        ("dermal_ld50", "measured"),
        ("pubchem", "measured"),
    ],
    "Acute Aquatic Toxicity": [
        ("aquatic_lc50", "measured"),
        ("pubchem", "measured"),
        ("ecosar", "predicted"),
    ],
    "Bioconcentration/ Bioaccumulation": [
        ("bcf", "measured"),
        ("log_kow", "measured"),
        ("opera_bcf", "predicted"),
        ("opera_logkow", "predicted"),
    ],
    "Persistence": [
        ("biodeg_half_life", "measured"),
        ("opera_biodeg", "predicted"),
    ],
    "Vapor Pressure": [
        ("vapor_pressure", "measured"),
        ("pubchem", "measured"),
        ("sds", "measured"),
        ("hspip", "predicted"),
    ],
    "Flammability: Liquid": [
        ("flash_point", "measured"),
        ("nfpa_fire", "measured"),
        ("pubchem", "measured"),
        ("sds", "measured"),
        ("flash_predict", "predicted"),
    ],
    "Atmospheric Hazard": [
        ("gwp100", "measured"),
        ("ipcc", "measured"),
    ],
    "Ozone Depletor": [
        ("odp", "measured"),
        ("montreal", "measured"),
    ],
    "Carcinogen": [
        ("iarc", "measured"),
        ("ghs_h_codes", "measured"),
    ],
}


@dataclass
class GapFillResult:
    """Result of gap-fill for one subcategory."""

    subcategory: str
    endpoint: str | None = None
    value: float | str | None = None
    source: str | None = None
    predicted: bool = False
    pathway: str | None = None
    alternatives: list[Evidence] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "subcategory": self.subcategory,
            "endpoint": self.endpoint,
            "value": self.value,
            "source": self.source,
            "predicted": self.predicted,
            "pathway": self.pathway,
            "alternatives_count": len(self.alternatives),
        }


class GapFillLayer:
    """
    Gap-fill layer for auto_p2oasys.

    Applies prediction/gap-fill strategies when measured data is unavailable.
    """

    def __init__(self, evidence: list[Evidence]):
        """Initialize with gathered evidence."""
        self.evidence = evidence
        self._index = self._build_index()

    def _build_index(self) -> dict[str, list[Evidence]]:
        """Index evidence by endpoint."""
        index: dict[str, list[Evidence]] = {}
        for ev in self.evidence:
            endpoint = ev.endpoint.lower()
            if endpoint not in index:
                index[endpoint] = []
            index[endpoint].append(ev)
        return index

    def fill(self, subcategory: str) -> GapFillResult:
        """
        Apply gap-fill for a subcategory.

        Tries pathways in order, returns first reliable one.
        """
        pathways = SUBCATEGORY_PATHWAYS.get(subcategory, [])

        result = GapFillResult(subcategory=subcategory)

        for pathway_name, pathway_type in pathways:
            evidence_list = self._index.get(pathway_name.lower(), [])

            if pathway_type == "measured":
                measured = [e for e in evidence_list if not e.predicted]
                if measured:
                    best = measured[0]
                    result.endpoint = best.endpoint
                    result.value = best.value
                    result.source = best.source
                    result.predicted = False
                    result.pathway = pathway_name
                    result.alternatives = measured[1:] + [
                        e for e in evidence_list if e.predicted
                    ]
                    return result

            elif pathway_type == "predicted":
                if evidence_list:
                    best = evidence_list[0]
                    result.endpoint = best.endpoint
                    result.value = best.value
                    result.source = best.source
                    result.predicted = True
                    result.pathway = pathway_name
                    result.alternatives = evidence_list[1:]
                    return result

        return result

    def fill_all(self) -> dict[str, GapFillResult]:
        """Apply gap-fill for all subcategories."""
        results = {}
        for category, subcats in AUTO6_CATEGORIES.items():
            for subcat in subcats:
                results[subcat] = self.fill(subcat)
        return results
