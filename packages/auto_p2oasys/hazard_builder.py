"""
Build hazard_data dict from Evidence records.

The hazard_data structure expected by the P2OASys scorer is complex.
This module translates Evidence records into that format.
"""

from __future__ import annotations

import re
from typing import Optional

from .evidence import Evidence


class HazardDataBuilder:
    """
    Build hazard_data dict incrementally from Evidence records.

    The scorer expects hazard_data with structure:
    {
        "toxicities": [{value, source, predicted, route?}],
        "ghs": {"h_codes": [...]},
        "hazard_metrics": {
            "flash_point": [...],
            "vapor_pressure_mmhg": [...],
            "nfpa": [...],
            "gwp100": [...],
            "odp": [...],
            "log_kow": ...,
            "bcf_l_kg": ...,
        },
        "molecular_weight": ...,
        "smiles": ...,
        "cid": ...,
    }
    """

    def __init__(self, cas: str):
        self.cas = cas
        self.toxicities: list[dict] = []
        self.h_codes: list[str] = []
        self.flash_points: list[str] = []
        self.vapor_pressures: list[float] = []
        self.nfpa: list[str] = []
        self.gwp100: list[float] = []
        self.odp: list[float] = []
        self.iarc: list[str] = []
        self.epa_carcinogen: list[str] = []
        self.log_kow: float | None = None
        self.bcf_l_kg: float | None = None
        self.biodeg_half_life_days: float | None = None
        self.molecular_weight: float | None = None
        self.smiles: str | None = None
        self.cid: int | None = None
        self.pka: float | None = None
        self.aquatic_lc50: list[dict] = []
        self.chronic_aquatic_noec: list[dict] = []
        self.genotoxicity: list[dict] = []
        self.repeated_dose: list[dict] = []
        self.odor_threshold: float | None = None
        self.not_wired: dict[str, str] = {}
        self.iuclid_sources: list[str] = []

    def add_evidence(self, ev: Evidence) -> None:
        """Add an Evidence record to the builder."""
        endpoint = ev.endpoint.lower()

        if "oral" in endpoint and ("ld50" in endpoint or "ldlo" in endpoint):
            self._add_toxicity(ev, "oral")
        elif "dermal" in endpoint and ("ld50" in endpoint or "ldlo" in endpoint):
            self._add_toxicity(ev, "dermal")
        elif "inhalation" in endpoint and ("lc50" in endpoint or "lclo" in endpoint):
            self._add_toxicity(ev, "inhalation")
        elif "aquatic" in endpoint or (
            "lc50" in endpoint and ("fish" in endpoint or "daphnia" in endpoint)
        ):
            self._add_aquatic(ev)
        elif endpoint in ("h_codes", "ghs_h_codes"):
            self._add_h_codes(ev)
        elif "flash" in endpoint:
            self._add_flash_point(ev)
        elif "vapor" in endpoint and "pressure" in endpoint:
            self._add_vapor_pressure(ev)
        elif "nfpa" in endpoint:
            self._add_nfpa(ev)
        elif endpoint in ("gwp", "gwp100", "gwp_100"):
            self._add_gwp(ev)
        elif endpoint in ("odp", "odp100"):
            self._add_odp(ev)
        elif endpoint in ("iarc", "iarc_group", "iarc_classification"):
            self._add_iarc(ev)
        elif endpoint in ("epa_carcinogen", "epa_class"):
            self._add_epa_carcinogen(ev)
        elif endpoint in ("log_kow", "logkow", "log_p", "logp"):
            self._add_log_kow(ev)
        elif endpoint in ("bcf", "bcf_l_kg", "bioconcentration"):
            self._add_bcf(ev)
        elif endpoint in ("biodeg", "biodeg_half_life", "half_life_days"):
            self._add_biodeg(ev)
        elif endpoint in ("molecular_weight", "mw"):
            self._add_mw(ev)
        elif endpoint == "smiles":
            if isinstance(ev.value, str):
                self.smiles = ev.value
        elif endpoint == "cid":
            if isinstance(ev.value, (int, float)):
                self.cid = int(ev.value)
        elif endpoint == "pka":
            if isinstance(ev.value, (int, float)):
                self.pka = float(ev.value)
        elif endpoint == "chronic_aquatic_noec":
            self._add_chronic_aquatic(ev)
        elif "genotoxicity" in endpoint:
            self._add_genotoxicity(ev)
        elif endpoint == "repeated_dose_toxicity":
            self._add_repeated_dose(ev)
        elif endpoint == "odor_threshold":
            self._add_odor_threshold(ev)
        elif ev.source == "NOT_WIRED":
            self.not_wired[endpoint] = ev.reference or "Not yet implemented"

        if ev.source and "ECHA" in ev.source:
            self.iuclid_sources.append(ev.source)

    def _add_toxicity(self, ev: Evidence, route: str) -> None:
        """Add a toxicity record."""
        val_str = self._format_tox_value(ev, route)
        if val_str:
            self.toxicities.append(
                {
                    "value": val_str,
                    "source": ev.source,
                    "predicted": ev.predicted,
                    "route": route,
                }
            )

    def _format_tox_value(self, ev: Evidence, route: str) -> str | None:
        """Format toxicity value for scorer."""
        if ev.value is None:
            return None

        parts = []
        if "ld50" in ev.endpoint.lower():
            parts.append("LD50")
        elif "lc50" in ev.endpoint.lower():
            parts.append("LC50")
        else:
            parts.append(ev.endpoint)

        if ev.qualifier:
            parts.append(ev.qualifier)

        parts.append(str(ev.value))

        if ev.unit:
            parts.append(ev.unit)

        if route:
            parts.append(route)

        return " ".join(parts)

    def _add_aquatic(self, ev: Evidence) -> None:
        """Add aquatic toxicity."""
        if ev.value is not None:
            try:
                val = float(ev.value)
                self.aquatic_lc50.append(
                    {
                        "value": val,
                        "unit": ev.unit or "mg/L",
                        "source": ev.source,
                        "predicted": ev.predicted,
                    }
                )
            except (TypeError, ValueError):
                pass

    def _add_h_codes(self, ev: Evidence) -> None:
        """Add GHS H-codes."""
        if isinstance(ev.value, list):
            self.h_codes.extend(ev.value)
        elif isinstance(ev.value, str):
            codes = re.findall(r"H\d{3}[A-Z]?", ev.value)
            self.h_codes.extend(codes)

    def _add_flash_point(self, ev: Evidence) -> None:
        """Add flash point."""
        if ev.value is not None:
            val_str = str(ev.value)
            if ev.unit:
                val_str += f" {ev.unit}"
            self.flash_points.append(val_str)

    def _add_vapor_pressure(self, ev: Evidence) -> None:
        """Add vapor pressure."""
        if ev.value is not None:
            try:
                self.vapor_pressures.append(float(ev.value))
            except (TypeError, ValueError):
                pass

    def _add_nfpa(self, ev: Evidence) -> None:
        """Add NFPA rating."""
        if ev.value is not None:
            val = str(ev.value)
            if "health" in ev.endpoint.lower():
                self.nfpa.append(f"{val} - Health")
            elif "fire" in ev.endpoint.lower() or "flame" in ev.endpoint.lower():
                self.nfpa.append(f"{val} - Fire")
            else:
                self.nfpa.append(val)

    def _add_gwp(self, ev: Evidence) -> None:
        """Add GWP100."""
        if ev.value is not None:
            try:
                self.gwp100.append(float(ev.value))
            except (TypeError, ValueError):
                pass

    def _add_odp(self, ev: Evidence) -> None:
        """Add ODP."""
        if ev.value is not None:
            try:
                self.odp.append(float(ev.value))
            except (TypeError, ValueError):
                pass

    def _add_iarc(self, ev: Evidence) -> None:
        """Add IARC classification."""
        if ev.value is not None:
            self.iarc.append(str(ev.value))

    def _add_epa_carcinogen(self, ev: Evidence) -> None:
        """Add EPA carcinogen classification."""
        if ev.value is not None:
            self.epa_carcinogen.append(str(ev.value))

    def _add_chronic_aquatic(self, ev: Evidence) -> None:
        """Add chronic aquatic NOEC."""
        if ev.value is not None:
            try:
                val = float(ev.value)
                self.chronic_aquatic_noec.append(
                    {
                        "value": val,
                        "unit": ev.unit or "mg/L",
                        "source": ev.source,
                        "predicted": ev.predicted,
                    }
                )
            except (TypeError, ValueError):
                pass

    def _add_genotoxicity(self, ev: Evidence) -> None:
        """Add genotoxicity data."""
        self.genotoxicity.append(
            {
                "value": ev.value,
                "endpoint": ev.endpoint,
                "source": ev.source,
                "predicted": ev.predicted,
            }
        )

    def _add_repeated_dose(self, ev: Evidence) -> None:
        """Add repeated dose toxicity."""
        if ev.value is not None:
            self.repeated_dose.append(
                {
                    "value": ev.value,
                    "unit": ev.unit or "mg/kg/day",
                    "source": ev.source,
                    "qualifier": ev.qualifier,
                    "predicted": ev.predicted,
                }
            )

    def _add_odor_threshold(self, ev: Evidence) -> None:
        """Add odor threshold."""
        if ev.value is not None and self.odor_threshold is None:
            try:
                self.odor_threshold = float(ev.value)
            except (TypeError, ValueError):
                pass

    def _add_log_kow(self, ev: Evidence) -> None:
        """Add Log Kow."""
        if ev.value is not None and self.log_kow is None:
            try:
                self.log_kow = float(ev.value)
            except (TypeError, ValueError):
                pass

    def _add_bcf(self, ev: Evidence) -> None:
        """Add BCF."""
        if ev.value is not None and self.bcf_l_kg is None:
            try:
                self.bcf_l_kg = float(ev.value)
            except (TypeError, ValueError):
                pass

    def _add_biodeg(self, ev: Evidence) -> None:
        """Add biodegradation half-life."""
        if ev.value is not None and self.biodeg_half_life_days is None:
            try:
                self.biodeg_half_life_days = float(ev.value)
            except (TypeError, ValueError):
                pass

    def _add_mw(self, ev: Evidence) -> None:
        """Add molecular weight."""
        if ev.value is not None and self.molecular_weight is None:
            try:
                self.molecular_weight = float(ev.value)
            except (TypeError, ValueError):
                pass

    def build(self) -> dict:
        """Build the final hazard_data dict."""
        if self.aquatic_lc50:
            for aq in self.aquatic_lc50:
                self.toxicities.append(
                    {
                        "value": f"LC50 fish {aq['value']} {aq['unit']}",
                        "source": aq.get("source", "unknown"),
                        "predicted": aq.get("predicted", False),
                    }
                )

        for iarc_val in self.iarc:
            self.toxicities.append(
                {
                    "value": f"IARC Group {iarc_val}",
                    "source": "IARC",
                }
            )

        for epa_val in self.epa_carcinogen:
            self.toxicities.append(
                {
                    "value": f"EPA Carcinogen Category {epa_val}",
                    "source": "EPA IRIS",
                }
            )

        for noec in self.chronic_aquatic_noec:
            self.toxicities.append(
                {
                    "value": f"Chronic NOEC {noec['value']} {noec['unit']}",
                    "source": noec.get("source", "unknown"),
                    "predicted": noec.get("predicted", False),
                }
            )

        for geno in self.genotoxicity:
            self.toxicities.append(
                {
                    "value": f"Genotoxicity: {geno['value']} ({geno['endpoint']})",
                    "source": geno.get("source", "unknown"),
                    "predicted": geno.get("predicted", False),
                }
            )

        for rd in self.repeated_dose:
            qual = f"{rd['qualifier']} " if rd.get("qualifier") else ""
            self.toxicities.append(
                {
                    "value": f"Repeated dose: {qual}{rd['value']} {rd['unit']}",
                    "source": rd.get("source", "unknown"),
                    "predicted": rd.get("predicted", False),
                }
            )

        hazard_data = {
            "toxicities": self.toxicities,
            "ghs": {"h_codes": list(set(self.h_codes))},
            "hazard_metrics": {
                "flash_point": self.flash_points,
                "vapor_pressure_mmhg": self.vapor_pressures,
                "nfpa": self.nfpa,
                "gwp100": self.gwp100,
                "odp": self.odp,
            },
        }

        if self.log_kow is not None:
            hazard_data["log_kow"] = self.log_kow
            hazard_data["hazard_metrics"]["log_kow"] = self.log_kow

        if self.bcf_l_kg is not None:
            hazard_data["bcf_l_kg"] = self.bcf_l_kg
            hazard_data["hazard_metrics"]["bcf_l_kg"] = self.bcf_l_kg

        if self.biodeg_half_life_days is not None:
            hazard_data["biodeg_half_life_days"] = self.biodeg_half_life_days

        if self.molecular_weight is not None:
            hazard_data["molecular_weight"] = self.molecular_weight

        if self.smiles:
            hazard_data["smiles"] = self.smiles

        if self.cid:
            hazard_data["cid"] = self.cid

        if self.pka is not None:
            hazard_data["pKa"] = self.pka

        if self.odor_threshold is not None:
            hazard_data["odor_threshold_ppm"] = self.odor_threshold
            hazard_data["hazard_metrics"]["odor_threshold"] = self.odor_threshold

        if self.not_wired:
            hazard_data["not_wired_endpoints"] = self.not_wired

        if self.iuclid_sources:
            hazard_data["iuclid_attribution"] = list(set(self.iuclid_sources))

        return hazard_data
