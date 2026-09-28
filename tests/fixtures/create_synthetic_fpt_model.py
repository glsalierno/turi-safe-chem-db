#!/usr/bin/env python3
"""
Create synthetic flash point model fixtures for offline testing.

This creates minimal valid joblib files that can be loaded to test
the fpt_predict module WITHOUT the real licensed models.

DO NOT use these for actual predictions - they are for testing only.
"""

import sys
from pathlib import Path

import numpy as np


def create_synthetic_fixtures(output_dir: Path):
    """Create synthetic model files for testing."""
    try:
        import joblib
    except ImportError:
        print("joblib not available - skipping fixture creation")
        return False
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    class MockModel:
        """Mock XGBoost model that returns constant predictions."""
        def predict(self, X):
            return np.full(len(X), 300.0)
    
    class MockScaler:
        """Mock scaler that returns input unchanged."""
        def transform(self, X):
            return X
    
    joblib.dump(MockModel(), output_dir / "fpt_model_zenodo10.joblib")
    joblib.dump(MockScaler(), output_dir / "fpt_scaler_zenodo10.joblib")
    
    feature_names = ["MolWt", "MolLogP", "TPSA", "NumRotatableBonds",
                     "NumHAcceptors", "NumHDonors", "NumAromaticRings", "FractionCSP3"]
    joblib.dump(feature_names, output_dir / "fpt_features.joblib")
    
    training_features = np.random.randn(100, 8)
    np.save(output_dir / "fpt_training_features.npy", training_features)
    
    print(f"Created synthetic fixtures in {output_dir}")
    return True


if __name__ == "__main__":
    output = Path(__file__).parent / "synthetic_fpt_models"
    create_synthetic_fixtures(output)
