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


class FlashPredictError(Exception):
    """Error from flash point prediction."""
    pass


def gather_flash_prediction(cas: str, measured_available: bool = False) -> list[Evidence]:
    """
    Gather flash point prediction from Maestri/Salierno model.

    Flash point routing: measured first, then Maestri model fallback.
    
    Model provenance:
    - Code: Zenodo 10.5281/zenodo.20931012 (CC-BY-4.0)
    - Training: DIPPR n=1248, R² 0.944, RMSE 14.81 K, MAE 8.01 K
    - Models trained on licensed data (HSPiP/DIPPR/Yaws) - NOT in repo

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
    status = predictor.get_status()
    
    if not status["available"]:
        return []

    try:
        smiles = _get_smiles_for_cas(cas)
        if not smiles:
            return []

        result = predictor.predict(smiles)
        if result is None:
            return []

        ad_label = ""
        if not result.in_domain:
            ad_label = " [OUT OF AD]"
        
        return [
            Evidence(
                cas=display_cas,
                endpoint="flash_point",
                value=result.flash_point_c,
                unit="°C",
                source="Predicted (Maestri FPT model)",
                predicted=True,
                reliability=f"AD: {'in-domain' if result.in_domain else 'OUT OF DOMAIN'}{ad_label}",
                reference="Zenodo 10.5281/zenodo.20931012 (R² 0.944, RMSE 14.81 K)",
                retrieved_at=now,
                raw_text=f"AD distance: {result.ad_distance:.3f}, threshold: {result.ad_threshold:.3f}",
            )
        ]
    except Exception as e:
        raise FlashPredictError(f"Flash point prediction failed: {e}") from e


def get_flash_model_status() -> dict:
    """Get detailed flash point model status for source report."""
    predictor = FlashPointPredictor.get_instance()
    return predictor.get_status()


class FlashPointPredictor:
    """
    Wrapper for Maestri/Salierno flash point prediction model.
    
    Model provenance:
    - Code: Zenodo 10.5281/zenodo.20931012 ("mlmaestri/VariablePrediction", CC-BY-4.0)
    - Training data: DIPPR flash point n=1248 (licensed, not redistributable)
    - Model metrics: R² 0.944, RMSE 14.81 K, MAE 8.01 K
    
    CRITICAL: Trained models (fpt_model_zenodo10.joblib etc.) are on licensed
    HSPiP/DIPPR/Yaws data and MUST NOT be committed to public repo.
    
    Set TURI_FPT_MODEL_DIR to directory containing model files.
    """

    _instance: Optional["FlashPointPredictor"] = None

    @classmethod
    def get_instance(cls) -> "FlashPointPredictor":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._fpt_module = None
        self._load_attempted = False
        self._load_error: str | None = None

    def _ensure_loaded(self) -> bool:
        """Attempt to load fpt_predict module."""
        if self._load_attempted:
            return self._fpt_module is not None
        
        self._load_attempted = True
        
        try:
            from packages import fpt_predict
            if fpt_predict.is_available():
                self._fpt_module = fpt_predict
                return True
            else:
                status = fpt_predict.get_model_status()
                self._load_error = status.get("reason", "Model not available")
                return False
        except ImportError as e:
            self._load_error = f"fpt_predict module not available: {e}"
            return False
        except Exception as e:
            self._load_error = f"Failed to load fpt_predict: {e}"
            return False

    def is_available(self) -> bool:
        """Check if model is available and loaded."""
        return self._ensure_loaded()

    def get_status(self) -> dict:
        """Get detailed model status for reporting."""
        if not self._load_attempted:
            self._ensure_loaded()
        
        if self._fpt_module is not None:
            try:
                return self._fpt_module.get_model_status()
            except Exception:
                pass
        
        return {
            "available": False,
            "status": "NOT_CONFIGURED",
            "reason": self._load_error or "Model not loaded",
        }

    def predict(self, smiles: str):
        """
        Predict flash point from SMILES.
        
        Returns FPTResult or None if prediction fails.
        """
        if not self.is_available():
            return None
        
        try:
            return self._fpt_module.predict(smiles)
        except Exception:
            return None
