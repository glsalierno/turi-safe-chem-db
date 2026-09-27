"""
Fast P2OASys pipeline: evidence gathering, hazard_data building, and scoring.

This module orchestrates the adapters to gather evidence for a CAS number,
builds the hazard_data dict expected by the P2OASys scorer, and runs the scorer.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from .evidence import Evidence
from .source_report import SourceReport, AdapterStatus


ADAPTER_ORDER = [
    "expert_lookup",
    "pubchem_identity",
    "pubchem_hazard",
    "cameo_nfpa",
    "iarc",
    "odp_gwp",
    "caa_hap",
    "sds_parse",
    "toxvaldb",
    "cpdb",
    "iuclid",
    "opera",
    "ecosar",
    "hspip_vp",
    "flash_predict",
    "ph_cascade",
]

AUTO6_CATEGORIES = [
    "Acute Human Effects",
    "Chronic Human Effects",
    "Ecological Hazards",
    "Environmental Fate & Transport",
    "Atmospheric Hazard",
    "Physical Properties",
]


def gather_evidence(
    cas: str,
    sds_pdf: Path | None = None,
    report: SourceReport | None = None,
) -> list[Evidence]:
    """
    Gather evidence from all available adapters.

    Adapters are run in priority order. Each adapter may contribute
    multiple Evidence records. Adapters that fail are recorded in
    the source report.

    Args:
        cas: CAS registry number (normalized)
        sds_pdf: Optional SDS PDF path
        report: Source report to record adapter status

    Returns:
        List of Evidence records from all adapters
    """
    if report is None:
        report = SourceReport()

    evidence: list[Evidence] = []

    from .adapters import pubchem as pubchem_adapter
    from .adapters import cameo as cameo_adapter
    from .adapters import lookup_tables as lookup_adapter
    from .adapters import sds as sds_adapter
    from .adapters import predictions as predict_adapter

    try:
        start = time.monotonic()
        pc_evidence = pubchem_adapter.gather_identity(cas)
        pc_evidence.extend(pubchem_adapter.gather_hazard(cas))
        duration = (time.monotonic() - start) * 1000
        if pc_evidence:
            evidence.extend(pc_evidence)
            report.add(
                "pubchem",
                AdapterStatus.RAN,
                evidence_count=len(pc_evidence),
                duration_ms=duration,
            )
        else:
            report.add("pubchem", AdapterStatus.NO_DATA, "No data found")
    except Exception as e:
        report.add("pubchem", AdapterStatus.ERROR, str(e))

    try:
        start = time.monotonic()
        cameo_evidence = cameo_adapter.gather_nfpa(cas)
        duration = (time.monotonic() - start) * 1000
        if cameo_evidence:
            evidence.extend(cameo_evidence)
            report.add(
                "cameo_nfpa",
                AdapterStatus.RAN,
                evidence_count=len(cameo_evidence),
                duration_ms=duration,
            )
        else:
            report.add("cameo_nfpa", AdapterStatus.NO_DATA, "CAS not in CAMEO database")
    except Exception as e:
        report.add("cameo_nfpa", AdapterStatus.ERROR, str(e))

    try:
        start = time.monotonic()
        lookup_evidence = lookup_adapter.gather_iarc(cas)
        lookup_evidence.extend(lookup_adapter.gather_epa_carcinogen(cas))
        lookup_evidence.extend(lookup_adapter.gather_odp_gwp(cas))
        lookup_evidence.extend(lookup_adapter.gather_hap(cas))
        lookup_evidence.extend(lookup_adapter.gather_odor_threshold(cas))
        duration = (time.monotonic() - start) * 1000
        if lookup_evidence:
            evidence.extend(lookup_evidence)
            report.add(
                "lookup_tables",
                AdapterStatus.RAN,
                evidence_count=len(lookup_evidence),
                duration_ms=duration,
            )
        else:
            report.add(
                "lookup_tables", AdapterStatus.NO_DATA, "No entries in lookup tables"
            )
    except Exception as e:
        report.add("lookup_tables", AdapterStatus.ERROR, str(e))

    try:
        not_wired_evidence = lookup_adapter.gather_idlh(cas)
        not_wired_evidence.extend(lookup_adapter.gather_reportable_quantity(cas))
        evidence.extend(not_wired_evidence)
        report.add(
            "not_wired_endpoints",
            AdapterStatus.SKIPPED,
            reason="IDLH and Reportable Quantity NOT_WIRED",
            evidence_count=len(not_wired_evidence),
        )
    except Exception as e:
        report.add("not_wired_endpoints", AdapterStatus.ERROR, str(e))

    if sds_pdf is not None:
        try:
            start = time.monotonic()
            sds_evidence = sds_adapter.parse_sds(sds_pdf, cas)
            duration = (time.monotonic() - start) * 1000
            if sds_evidence:
                evidence.extend(sds_evidence)
                report.add(
                    "sds_parse",
                    AdapterStatus.RAN,
                    evidence_count=len(sds_evidence),
                    duration_ms=duration,
                )
            else:
                report.add("sds_parse", AdapterStatus.NO_DATA, "No data extracted")
        except Exception as e:
            report.add("sds_parse", AdapterStatus.ERROR, str(e))

    try:
        start = time.monotonic()
        opera_evidence = predict_adapter.gather_opera(cas)
        duration = (time.monotonic() - start) * 1000
        if opera_evidence:
            evidence.extend(opera_evidence)
            report.add(
                "opera",
                AdapterStatus.RAN,
                evidence_count=len(opera_evidence),
                duration_ms=duration,
            )
        else:
            report.add("opera", AdapterStatus.SKIPPED, "OPERA cache not available")
    except Exception as e:
        report.add("opera", AdapterStatus.ERROR, str(e))

    try:
        start = time.monotonic()
        ecosar_evidence = predict_adapter.gather_ecosar(cas)
        duration = (time.monotonic() - start) * 1000
        if ecosar_evidence:
            evidence.extend(ecosar_evidence)
            report.add(
                "ecosar",
                AdapterStatus.RAN,
                evidence_count=len(ecosar_evidence),
                duration_ms=duration,
            )
        else:
            report.add("ecosar", AdapterStatus.SKIPPED, "ECOSAR not available")
    except Exception as e:
        report.add("ecosar", AdapterStatus.ERROR, str(e))

    report.add(
        "flash_predict",
        AdapterStatus.SKIPPED,
        reason="Maestri/Salierno model not yet provided (TODO)",
    )

    report.add(
        "hspip_vp",
        AdapterStatus.DISABLED,
        reason="HSPiP licensed, optional",
    )

    from .adapters import iuclid as iuclid_adapter

    try:
        if iuclid_adapter.is_iuclid_available():
            start = time.monotonic()
            iuclid_evidence = iuclid_adapter.gather_iuclid(cas)
            duration = (time.monotonic() - start) * 1000
            if iuclid_evidence:
                evidence.extend(iuclid_evidence)
                report.add(
                    "iuclid",
                    AdapterStatus.RAN,
                    evidence_count=len(iuclid_evidence),
                    duration_ms=duration,
                    reason="ECHA REACH Study Results",
                )
            else:
                report.add("iuclid", AdapterStatus.NO_DATA, "CAS not in IUCLID cache")
        else:
            report.add(
                "iuclid",
                AdapterStatus.SKIPPED,
                reason="IUCLID cache not available (set IUCLID_CACHE_DB)",
            )
    except Exception as e:
        report.add("iuclid", AdapterStatus.ERROR, str(e))

    report.add(
        "toxvaldb",
        AdapterStatus.SKIPPED,
        reason="API key required for CompTox ToxValDB",
    )

    report.add(
        "cpdb",
        AdapterStatus.SKIPPED,
        reason="CPDB sqlite not bundled",
    )

    return evidence


def build_hazard_data(cas: str, evidence: list[Evidence]) -> dict:
    """
    Build hazard_data dict from Evidence records.

    The hazard_data dict is the input format expected by the P2OASys scorer.
    It has keys: toxicities, ghs, hazard_metrics, molecular_weight, etc.

    Args:
        cas: CAS registry number
        evidence: List of Evidence records

    Returns:
        hazard_data dict for the scorer
    """
    from .hazard_builder import HazardDataBuilder

    builder = HazardDataBuilder(cas)
    for ev in evidence:
        builder.add_evidence(ev)

    return builder.build()


def run_scorer(hazard_data: dict) -> tuple[dict | None, dict]:
    """
    Run the P2OASys scorer on hazard_data.

    Args:
        hazard_data: Dict in the format expected by the scorer

    Returns:
        (scores_dict, trace_dict) or (None, {}) on failure
    """
    try:
        from packages.p2oasys_scorer import (
            load_p2oasys_matrix,
            compute_p2oasys_scores_with_trace,
            DEFAULT_MATRIX_PATH,
        )

        if not DEFAULT_MATRIX_PATH.exists():
            return None, {"error": f"Matrix not found: {DEFAULT_MATRIX_PATH}"}

        matrix = load_p2oasys_matrix(DEFAULT_MATRIX_PATH)
        scores, trace = compute_p2oasys_scores_with_trace(hazard_data, matrix)
        return scores, trace

    except ImportError as e:
        return None, {"error": f"Scorer import failed: {e}"}
    except Exception as e:
        return None, {"error": f"Scorer failed: {e}"}
