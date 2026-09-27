"""
PubChem adapter for auto_p2oasys.

Wraps packages.doss_core.pubchem with throttle-safe fetching.
Provides identity (CID, SMILES, MW) and hazard data (GHS, NFPA, physchem).
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

from ..evidence import Evidence
from ..cas_utils import format_cas_display


_OFFLINE_MODE = os.environ.get("AUTO_P2OASYS_OFFLINE", "").lower() in ("1", "true")


def gather_identity(cas: str) -> list[Evidence]:
    """
    Gather identity evidence from PubChem.

    Returns CID, SMILES, molecular weight, name.
    """
    if _OFFLINE_MODE:
        return []

    evidence: list[Evidence] = []
    display_cas = format_cas_display(cas)
    now = datetime.now(timezone.utc)

    try:
        from packages.doss_core.pubchem import (
            get_cid_by_cas,
            get_compound_properties,
            PubChemNotFoundError,
            PubChemThrottledError,
        )

        cid = get_cid_by_cas(display_cas)
        if cid is None:
            return []

        evidence.append(
            Evidence(
                cas=display_cas,
                endpoint="cid",
                value=cid,
                source="PubChem",
                predicted=False,
                retrieved_at=now,
            )
        )

        props = get_compound_properties(cid)

        if props.get("MolecularWeight"):
            evidence.append(
                Evidence(
                    cas=display_cas,
                    endpoint="molecular_weight",
                    value=props["MolecularWeight"],
                    unit="g/mol",
                    source="PubChem",
                    predicted=False,
                    retrieved_at=now,
                )
            )

        smiles = (
            props.get("CanonicalSMILES")
            or props.get("IsomericSMILES")
            or props.get("ConnectivitySMILES")
        )
        if smiles:
            evidence.append(
                Evidence(
                    cas=display_cas,
                    endpoint="smiles",
                    value=smiles,
                    source="PubChem",
                    predicted=False,
                    retrieved_at=now,
                )
            )

    except ImportError:
        pass
    except Exception:
        pass

    return evidence


def gather_hazard(cas: str) -> list[Evidence]:
    """
    Gather hazard evidence from PubChem PUG View.

    Returns GHS H-codes, NFPA ratings, flash point, vapor pressure, toxicity.
    """
    if _OFFLINE_MODE:
        return []

    evidence: list[Evidence] = []
    display_cas = format_cas_display(cas)
    now = datetime.now(timezone.utc)

    try:
        from packages.doss_core.pubchem import (
            fetch_compound_data,
            parse_numeric_with_unit,
            PubChemNotFoundError,
            PubChemThrottledError,
        )

        data = fetch_compound_data(display_cas)

        h_codes = data.get("ghs_hazards", [])
        if h_codes:
            evidence.append(
                Evidence(
                    cas=display_cas,
                    endpoint="h_codes",
                    value=h_codes,
                    source="PubChem",
                    predicted=False,
                    retrieved_at=now,
                )
            )

        nfpa_health = data.get("nfpa_health")
        if nfpa_health is not None:
            evidence.append(
                Evidence(
                    cas=display_cas,
                    endpoint="nfpa_health",
                    value=nfpa_health,
                    source="PubChem",
                    predicted=False,
                    retrieved_at=now,
                )
            )

        nfpa_flame = data.get("nfpa_flame")
        if nfpa_flame is not None:
            evidence.append(
                Evidence(
                    cas=display_cas,
                    endpoint="nfpa_fire",
                    value=nfpa_flame,
                    source="PubChem",
                    predicted=False,
                    retrieved_at=now,
                )
            )

        props = data.get("properties", {})

        flash_point = props.get("Flash Point")
        if flash_point:
            fp_val = parse_numeric_with_unit(flash_point)
            if fp_val is not None:
                evidence.append(
                    Evidence(
                        cas=display_cas,
                        endpoint="flash_point",
                        value=fp_val,
                        unit="°C",
                        source="PubChem",
                        predicted=False,
                        raw_text=flash_point,
                        retrieved_at=now,
                    )
                )

        vp = props.get("Vapor Pressure")
        if vp:
            vp_val = parse_numeric_with_unit(vp)
            if vp_val is not None:
                evidence.append(
                    Evidence(
                        cas=display_cas,
                        endpoint="vapor_pressure",
                        value=vp_val,
                        unit="mmHg",
                        source="PubChem",
                        predicted=False,
                        raw_text=vp,
                        retrieved_at=now,
                    )
                )

        oral_tox = props.get("Acute Oral Toxicity")
        if oral_tox:
            tox_val = parse_numeric_with_unit(oral_tox)
            if tox_val is not None:
                evidence.append(
                    Evidence(
                        cas=display_cas,
                        endpoint="oral_ld50",
                        value=tox_val,
                        unit="mg/kg",
                        source="PubChem",
                        predicted=False,
                        raw_text=oral_tox,
                        retrieved_at=now,
                    )
                )

        dermal_tox = props.get("Acute Dermal Toxicity")
        if dermal_tox:
            tox_val = parse_numeric_with_unit(dermal_tox)
            if tox_val is not None:
                evidence.append(
                    Evidence(
                        cas=display_cas,
                        endpoint="dermal_ld50",
                        value=tox_val,
                        unit="mg/kg",
                        source="PubChem",
                        predicted=False,
                        raw_text=dermal_tox,
                        retrieved_at=now,
                    )
                )

        inhal_tox = props.get("Acute Inhalation Toxicity")
        if inhal_tox:
            tox_val = parse_numeric_with_unit(inhal_tox)
            if tox_val is not None:
                evidence.append(
                    Evidence(
                        cas=display_cas,
                        endpoint="inhalation_lc50",
                        value=tox_val,
                        unit="ppm",
                        source="PubChem",
                        predicted=False,
                        raw_text=inhal_tox,
                        retrieved_at=now,
                    )
                )

        log_p = props.get("LogP")
        if log_p:
            try:
                lp_val = float(log_p) if isinstance(log_p, (int, float)) else parse_numeric_with_unit(log_p)
                if lp_val is not None:
                    evidence.append(
                        Evidence(
                            cas=display_cas,
                            endpoint="log_kow",
                            value=lp_val,
                            source="PubChem",
                            predicted=False,
                            retrieved_at=now,
                        )
                    )
            except (TypeError, ValueError):
                pass

    except ImportError:
        pass
    except Exception:
        pass

    return evidence
