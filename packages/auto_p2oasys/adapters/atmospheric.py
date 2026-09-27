"""
Atmospheric hazard adapters for auto_p2oasys.

Provides:
- IPCC GWP (Global Warming Potential) lookup
- Atmospheric rules (acid rain, NESHAP, etc.)
- pH cascade for pH scoring
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..evidence import Evidence
from ..cas_utils import normalize_cas, format_cas_display


def _get_atmo_dir() -> Path | None:
    """Find atmospheric data directory."""
    env_path = os.environ.get("ATMO_DIR", "").strip()
    if env_path and Path(env_path).is_dir():
        return Path(env_path)

    try:
        from packages.p2oasys_scorer import config

        if hasattr(config, "ATMO_DIR") and Path(config.ATMO_DIR).is_dir():
            return Path(config.ATMO_DIR)
    except ImportError:
        pass

    candidates = [
        Path(__file__).resolve().parents[2] / "p2oasys_scorer" / "data" / "atmo",
        Path(__file__).resolve().parents[3] / "data" / "atmo",
    ]
    for path in candidates:
        if path.is_dir():
            return path

    return None


def is_ipcc_available() -> bool:
    """Check if IPCC GWP data is available."""
    atmo_dir = _get_atmo_dir()
    if atmo_dir is None:
        return False

    parquet = atmo_dir / "IPCC_v1.1.1_27ba917.parquet"
    xlsx = atmo_dir / "IPCC_AR4-AR6_GWPs.xlsx"

    return parquet.is_file() or xlsx.is_file()


def gather_ipcc_gwp(cas: str) -> list[Evidence]:
    """
    Gather GWP100 from IPCC data.

    Uses the IPCC AR4-AR6 GWP tables from the atmo folder.
    """
    atmo_dir = _get_atmo_dir()
    if atmo_dir is None:
        return []

    evidence: list[Evidence] = []
    display_cas = format_cas_display(cas)
    digits = normalize_cas(cas)
    now = datetime.now(timezone.utc)

    try:
        parquet = atmo_dir / "IPCC_v1.1.1_27ba917.parquet"
        if parquet.is_file():
            import pandas as pd

            df = pd.read_parquet(parquet)
            if "cas" in df.columns:
                df["cas_digits"] = df["cas"].astype(str).str.replace("-", "")
                row = df[df["cas_digits"] == digits]
                if not row.empty:
                    gwp = row.iloc[0].get("gwp100") or row.iloc[0].get("GWP100")
                    if gwp is not None:
                        evidence.append(
                            Evidence(
                                cas=display_cas,
                                endpoint="gwp100",
                                value=float(gwp),
                                source="IPCC",
                                predicted=False,
                                reference="IPCC AR6 GWP100",
                                retrieved_at=now,
                            )
                        )

    except Exception:
        pass

    return evidence


def apply_atmospheric_rules(cas: str, hazard_data: dict) -> list[Evidence]:
    """
    Apply atmospheric hazard rules.

    Includes:
    - Acid rain precursor heuristic (S, N compounds)
    - Default GWP/ODP for non-listed chemicals
    """
    evidence: list[Evidence] = []
    display_cas = format_cas_display(cas)
    now = datetime.now(timezone.utc)

    smiles = hazard_data.get("smiles", "")

    if smiles and ("S" in smiles or "N" in smiles):
        so2_potential = "S" in smiles and any(
            x in smiles.lower() for x in ["s=o", "so2", "so3", "sulfur"]
        )
        nox_potential = "N" in smiles and any(
            x in smiles.lower() for x in ["n=o", "no2", "nitrogen"]
        )

        if so2_potential or nox_potential:
            evidence.append(
                Evidence(
                    cas=display_cas,
                    endpoint="acid_rain_precursor",
                    value=True,
                    source="Atmospheric Rule",
                    predicted=True,
                    reference="Heuristic: S/N compound may form acid rain",
                    retrieved_at=now,
                )
            )

    gwp_values = hazard_data.get("hazard_metrics", {}).get("gwp100", [])
    odp_values = hazard_data.get("hazard_metrics", {}).get("odp", [])

    if not gwp_values:
        evidence.append(
            Evidence(
                cas=display_cas,
                endpoint="gwp100",
                value=0,
                source="Default",
                predicted=True,
                reference="Default GWP=0 for unlisted compound (not on authoritative list)",
                retrieved_at=now,
            )
        )

    if not odp_values:
        evidence.append(
            Evidence(
                cas=display_cas,
                endpoint="odp",
                value=0,
                source="Default",
                predicted=True,
                reference="Default ODP=0 for unlisted compound (not on authoritative list)",
                retrieved_at=now,
            )
        )

    return evidence


def estimate_ph(cas: str, hazard_data: dict) -> list[Evidence]:
    """
    Estimate pH using the pH cascade.

    Priority:
    1. Experimental 1% pH
    2. Experimental pKa
    3. OPERA predicted pKa
    4. Functional group SMARTS heuristic
    """
    evidence: list[Evidence] = []
    display_cas = format_cas_display(cas)
    now = datetime.now(timezone.utc)

    exp_ph = hazard_data.get("exp_ph_1pct")
    if exp_ph is not None:
        evidence.append(
            Evidence(
                cas=display_cas,
                endpoint="ph_estimate",
                value=exp_ph,
                source="Experimental",
                predicted=False,
                reference="1% solution pH",
                retrieved_at=now,
            )
        )
        return evidence

    pka = hazard_data.get("pKa")
    if pka is not None:
        if pka < 4:
            ph_est = 2 + (pka / 4) * 3
        elif pka > 10:
            ph_est = 10 + (14 - pka) / 4 * 2
        else:
            ph_est = 7.0

        evidence.append(
            Evidence(
                cas=display_cas,
                endpoint="ph_estimate",
                value=round(ph_est, 1),
                source="pKa Estimate",
                predicted=True,
                reference=f"Estimated from pKa={pka}",
                retrieved_at=now,
            )
        )
        return evidence

    smiles = hazard_data.get("smiles", "")
    if smiles:
        ph_est = _ph_from_smarts(smiles)
        if ph_est is not None:
            evidence.append(
                Evidence(
                    cas=display_cas,
                    endpoint="ph_estimate",
                    value=ph_est,
                    source="SMARTS Heuristic",
                    predicted=True,
                    reference="Functional group pH heuristic",
                    retrieved_at=now,
                )
            )
            return evidence

    return evidence


def _ph_from_smarts(smiles: str) -> float | None:
    """Estimate pH from functional groups in SMILES."""
    smiles_lower = smiles.lower()

    if "c(=o)o" in smiles_lower or "cooh" in smiles_lower:
        return 3.0
    if "s(=o)(=o)o" in smiles_lower or "so3h" in smiles_lower:
        return 1.0
    if "p(=o)(o)(o)o" in smiles_lower:
        return 2.0

    if "[nh4]" in smiles_lower or "n+" in smiles:
        return 9.0
    if "[oh-]" in smiles_lower or "[o-]" in smiles:
        return 12.0
    if "n" in smiles_lower and "c(=o)n" not in smiles_lower:
        return 9.0

    return None
