"""
Prediction adapters for auto_p2oasys.

Provides OPERA, ECOSAR, and other predictive model interfaces.
These adapters return predicted (not measured) evidence.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..evidence import Evidence
from ..cas_utils import normalize_cas, format_cas_display


def _get_opera_cache_path() -> Path | None:
    """Find OPERA precompute sqlite cache."""
    env_path = os.environ.get("OPERA_PRECOMPUTE_DB_PATH", "").strip()
    if env_path and Path(env_path).is_file():
        return Path(env_path)

    try:
        from packages.p2oasys_scorer import config

        if hasattr(config, "OPERA_PRECOMPUTE_DB_PATH"):
            cfg_path = Path(config.OPERA_PRECOMPUTE_DB_PATH)
            if cfg_path.is_file():
                return cfg_path
    except ImportError:
        pass

    return None


def gather_opera(cas: str) -> list[Evidence]:
    """
    Gather OPERA predictions from precomputed cache.

    Returns Log Kow, BCF, biodegradation half-life, etc. if available.
    All values are marked as predicted=True.
    """
    db_path = _get_opera_cache_path()
    if db_path is None:
        return []

    evidence: list[Evidence] = []
    display_cas = format_cas_display(cas)
    digits = normalize_cas(cas)
    now = datetime.now(timezone.utc)

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        row = conn.execute(
            """SELECT * FROM opera_cache
               WHERE cas = ? OR REPLACE(cas, '-', '') = ?
               LIMIT 1""",
            (display_cas, digits),
        ).fetchone()

        conn.close()

        if row is None:
            return []

        log_kow = row.get("LogP_pred") if "LogP_pred" in row.keys() else None
        if log_kow is not None:
            evidence.append(
                Evidence(
                    cas=display_cas,
                    endpoint="log_kow",
                    value=float(log_kow),
                    source="OPERA",
                    predicted=True,
                    reliability="OPERA 2.9",
                    retrieved_at=now,
                )
            )

        bcf = row.get("BCF_pred") if "BCF_pred" in row.keys() else None
        if bcf is not None:
            evidence.append(
                Evidence(
                    cas=display_cas,
                    endpoint="bcf",
                    value=float(bcf),
                    unit="L/kg",
                    source="OPERA",
                    predicted=True,
                    reliability="OPERA 2.9",
                    retrieved_at=now,
                )
            )

        biodeg = row.get("BioDeg_pred") if "BioDeg_pred" in row.keys() else None
        if biodeg is not None:
            evidence.append(
                Evidence(
                    cas=display_cas,
                    endpoint="biodeg_half_life",
                    value=float(biodeg),
                    unit="days",
                    source="OPERA",
                    predicted=True,
                    reliability="OPERA 2.9",
                    retrieved_at=now,
                )
            )

    except Exception:
        pass

    return evidence


def gather_ecosar(cas: str) -> list[Evidence]:
    """
    Gather ECOSAR aquatic toxicity predictions.

    Returns predicted LC50/EC50 for fish, daphnia, algae if available.
    Currently checks for pyepisuite API availability.
    """
    evidence: list[Evidence] = []
    display_cas = format_cas_display(cas)
    now = datetime.now(timezone.utc)

    ecosar_available = os.environ.get("ECOSAR_API_URL", "").strip()
    if not ecosar_available:
        return []

    try:
        smiles = _get_smiles_for_cas(cas)
        if not smiles:
            return []

        results = _call_ecosar_api(smiles)
        if not results:
            return []

        fish_lc50 = results.get("fish_lc50_mg_l")
        if fish_lc50 is not None:
            evidence.append(
                Evidence(
                    cas=display_cas,
                    endpoint="aquatic_lc50_fish",
                    value=fish_lc50,
                    unit="mg/L",
                    source="ECOSAR",
                    predicted=True,
                    reliability="ECOSAR via pyepisuite",
                    retrieved_at=now,
                )
            )

        daphnia_lc50 = results.get("daphnia_lc50_mg_l")
        if daphnia_lc50 is not None:
            evidence.append(
                Evidence(
                    cas=display_cas,
                    endpoint="aquatic_lc50_daphnia",
                    value=daphnia_lc50,
                    unit="mg/L",
                    source="ECOSAR",
                    predicted=True,
                    reliability="ECOSAR via pyepisuite",
                    retrieved_at=now,
                )
            )

    except Exception:
        pass

    return evidence


def _get_smiles_for_cas(cas: str) -> str | None:
    """Get SMILES for CAS from PubChem."""
    try:
        from packages.doss_core.pubchem import get_smiles_for_cas

        return get_smiles_for_cas(cas)
    except ImportError:
        pass
    except Exception:
        pass

    return None


def _call_ecosar_api(smiles: str) -> dict | None:
    """Call ECOSAR API via pyepisuite."""
    api_url = os.environ.get("ECOSAR_API_URL", "").strip()
    if not api_url:
        return None

    try:
        import requests

        resp = requests.post(
            f"{api_url}/ecosar",
            json={"smiles": smiles},
            timeout=30,
        )
        if resp.ok:
            return resp.json()
    except Exception:
        pass

    return None


def gather_flash_prediction(cas: str, measured_available: bool = False) -> list[Evidence]:
    """
    Gather flash point prediction from Maestri/Salierno model.

    Flash point routing: measured first, then Maestri model fallback.

    Args:
        cas: CAS registry number
        measured_available: If True, skip prediction (measured data exists)

    Returns:
        Predicted flash point evidence, or empty if measured available or model unavailable
    """
    if measured_available:
        return []

    display_cas = format_cas_display(cas)
    now = datetime.now(timezone.utc)

    predictor = FlashPointPredictor.get_instance()
    if not predictor.is_available():
        return []

    try:
        smiles = _get_smiles_for_cas(cas)
        if not smiles:
            return []

        result = predictor.predict(smiles)
        if result is None:
            return []

        return [
            Evidence(
                cas=display_cas,
                endpoint="flash_point",
                value=result.get("flash_point_c"),
                unit="°C",
                source="Maestri/Salierno Model",
                predicted=True,
                reliability=f"R²={result.get('r_squared', 'N/A')}",
                reference="Maestri/Salierno flash point prediction model",
                retrieved_at=now,
            )
        ]
    except Exception:
        return []


class FlashPointPredictor:
    """
    Placeholder for Maestri/Salierno flash point prediction model.

    This class will wrap the trained model once model files are provided.
    Currently registered in capabilities with status TODO.
    """

    _instance: Optional["FlashPointPredictor"] = None
    _model_loaded: bool = False

    @classmethod
    def get_instance(cls) -> "FlashPointPredictor":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._model = None
        self._model_loaded = False

    def is_available(self) -> bool:
        """Check if model is available and loaded."""
        return self._model_loaded

    def predict(self, smiles: str) -> dict | None:
        """
        Predict flash point from SMILES.

        Returns None until model files are provided.
        """
        if not self.is_available():
            return None

        return None
