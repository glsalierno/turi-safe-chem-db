"""
Flash Point Prediction using Maestri XGBoost model.

Model metrics on DIPPR flash point data (n=1248):
- R² = 0.944
- RMSE = 14.81 K
- MAE = 8.01 K

Requires TURI_FPT_MODEL_DIR to point to directory with model files.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


class FPTModelNotConfiguredError(Exception):
    """Raised when flash point model directory is not configured or models not found."""
    pass


@dataclass
class FPTModelBundle:
    """Container for loaded model components."""
    model: Any
    scaler: Any
    feature_names: list[str]
    training_features: np.ndarray
    ad_threshold: float


_MODEL_BUNDLE: FPTModelBundle | None = None
_MODEL_LOAD_ERROR: str | None = None


def _get_model_dir() -> Path | None:
    """Get model directory from capability_config."""
    try:
        from packages.capability_config import ExternalToolsConfig
        return ExternalToolsConfig.fpt_model_dir()
    except ImportError:
        import os
        path = os.environ.get("TURI_FPT_MODEL_DIR", "").strip()
        return Path(path) if path else None


def load_bundle(model_dir: Path | None = None) -> FPTModelBundle:
    """
    Load model bundle from directory.
    
    Args:
        model_dir: Path to model directory. If None, uses TURI_FPT_MODEL_DIR.
        
    Returns:
        FPTModelBundle with loaded model components.
        
    Raises:
        FPTModelNotConfiguredError: If model directory not set or files missing.
    """
    global _MODEL_BUNDLE, _MODEL_LOAD_ERROR
    
    if _MODEL_BUNDLE is not None:
        return _MODEL_BUNDLE
    
    if model_dir is None:
        model_dir = _get_model_dir()
    
    if model_dir is None:
        _MODEL_LOAD_ERROR = "TURI_FPT_MODEL_DIR not configured"
        raise FPTModelNotConfiguredError(_MODEL_LOAD_ERROR)
    
    if not model_dir.is_dir():
        _MODEL_LOAD_ERROR = f"Model directory not found: {model_dir}"
        raise FPTModelNotConfiguredError(_MODEL_LOAD_ERROR)
    
    model_path = model_dir / "fpt_model_zenodo10.joblib"
    scaler_path = model_dir / "fpt_scaler_zenodo10.joblib"
    features_path = model_dir / "fpt_features.joblib"
    training_path = model_dir / "fpt_training_features.npy"
    
    missing = []
    for p in [model_path, scaler_path]:
        if not p.is_file():
            missing.append(p.name)
    
    if missing:
        _MODEL_LOAD_ERROR = f"Model files missing: {', '.join(missing)}"
        raise FPTModelNotConfiguredError(_MODEL_LOAD_ERROR)
    
    try:
        import joblib
        
        model = joblib.load(model_path)
        scaler = joblib.load(scaler_path)
        
        feature_names = []
        if features_path.is_file():
            feature_names = joblib.load(features_path)
        
        training_features = None
        ad_threshold = 0.0
        if training_path.is_file():
            training_features = np.load(training_path)
            from .ad import compute_ad_threshold
            ad_threshold = compute_ad_threshold(training_features)
        
        _MODEL_BUNDLE = FPTModelBundle(
            model=model,
            scaler=scaler,
            feature_names=feature_names,
            training_features=training_features if training_features is not None else np.array([]),
            ad_threshold=ad_threshold,
        )
        _MODEL_LOAD_ERROR = None
        return _MODEL_BUNDLE
        
    except ImportError as e:
        _MODEL_LOAD_ERROR = f"joblib not available: {e}"
        raise FPTModelNotConfiguredError(_MODEL_LOAD_ERROR) from e
    except Exception as e:
        _MODEL_LOAD_ERROR = f"Failed to load models: {e}"
        raise FPTModelNotConfiguredError(_MODEL_LOAD_ERROR) from e


def is_available() -> bool:
    """Check if flash point model is available and loadable."""
    try:
        load_bundle()
        return True
    except FPTModelNotConfiguredError:
        return False


def get_model_status() -> dict:
    """Get detailed model status for reporting."""
    model_dir = _get_model_dir()
    
    if model_dir is None:
        return {
            "available": False,
            "status": "NOT_CONFIGURED",
            "reason": "TURI_FPT_MODEL_DIR not set",
        }
    
    if not model_dir.is_dir():
        return {
            "available": False,
            "status": "NOT_CONFIGURED",
            "reason": f"Directory not found: {model_dir}",
        }
    
    try:
        bundle = load_bundle()
        return {
            "available": True,
            "status": "AVAILABLE",
            "model_dir": str(model_dir),
            "has_ad": len(bundle.training_features) > 0,
            "ad_threshold": bundle.ad_threshold,
        }
    except FPTModelNotConfiguredError as e:
        return {
            "available": False,
            "status": "NOT_CONFIGURED",
            "reason": str(e),
        }


def _compute_features(smiles: str) -> np.ndarray | None:
    """
    Compute molecular features from SMILES for prediction.
    
    Uses RDKit descriptors if available.
    """
    try:
        from rdkit import Chem
        from rdkit.Chem import Descriptors
        
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        
        features = [
            Descriptors.MolWt(mol),
            Descriptors.MolLogP(mol),
            Descriptors.TPSA(mol),
            Descriptors.NumRotatableBonds(mol),
            Descriptors.NumHAcceptors(mol),
            Descriptors.NumHDonors(mol),
            Descriptors.NumAromaticRings(mol),
            Descriptors.FractionCSP3(mol),
        ]
        return np.array(features).reshape(1, -1)
        
    except ImportError:
        logger.warning("RDKit not available for feature computation")
        return None
    except Exception as e:
        logger.warning(f"Feature computation failed: {e}")
        return None


@dataclass
class FPTResult:
    """Result from flash point prediction."""
    flash_point_k: float
    flash_point_c: float
    in_domain: bool
    ad_distance: float
    ad_threshold: float
    confidence: str


def predict(smiles: str) -> FPTResult | None:
    """
    Predict flash point for a single SMILES.
    
    Args:
        smiles: SMILES string for the compound.
        
    Returns:
        FPTResult with prediction and applicability domain info,
        or None if prediction fails.
        
    Raises:
        FPTModelNotConfiguredError: If model not configured.
    """
    bundle = load_bundle()
    
    features = _compute_features(smiles)
    if features is None:
        return None
    
    try:
        scaled_features = bundle.scaler.transform(features)
        fp_k = bundle.model.predict(scaled_features)[0]
        fp_c = fp_k - 273.15
        
        from .ad import check_applicability_domain
        ad_result = check_applicability_domain(
            features[0],
            bundle.training_features,
            bundle.ad_threshold,
        )
        
        confidence = "high" if ad_result.in_domain else "low (out of AD)"
        
        return FPTResult(
            flash_point_k=float(fp_k),
            flash_point_c=float(fp_c),
            in_domain=ad_result.in_domain,
            ad_distance=ad_result.distance,
            ad_threshold=ad_result.threshold,
            confidence=confidence,
        )
        
    except Exception as e:
        logger.error(f"Prediction failed: {e}")
        return None


def predict_df(smiles_list: list[str]) -> list[FPTResult | None]:
    """
    Predict flash points for multiple SMILES.
    
    Args:
        smiles_list: List of SMILES strings.
        
    Returns:
        List of FPTResult or None for each SMILES.
    """
    return [predict(s) for s in smiles_list]
