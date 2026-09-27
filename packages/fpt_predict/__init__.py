"""
Maestri Flash Point Prediction Model.

Provides XGBoost-based flash point prediction with applicability domain checking.

Model Provenance:
- Code: Zenodo 10.5281/zenodo.20931012 ("mlmaestri/VariablePrediction: pre_release", CC-BY-4.0)
- Training data: DIPPR flash point n=1248 (licensed, not redistributable)
- Model metrics: R² 0.944, RMSE 14.81 K, MAE 8.01 K

CRITICAL: Trained models (fpt_model_zenodo10.joblib etc.) are trained on licensed
HSPiP/DIPPR/Yaws data and MUST NOT be committed to public repo.
Set TURI_FPT_MODEL_DIR environment variable to directory containing model files.
"""

from .predict import (
    predict,
    predict_df,
    load_bundle,
    is_available,
    get_model_status,
    FPTModelNotConfiguredError,
)
from .ad import (
    check_applicability_domain,
    ApplicabilityDomainResult,
)

__all__ = [
    "predict",
    "predict_df",
    "load_bundle",
    "is_available",
    "get_model_status",
    "FPTModelNotConfiguredError",
    "check_applicability_domain",
    "ApplicabilityDomainResult",
]

__version__ = "0.1.0"
