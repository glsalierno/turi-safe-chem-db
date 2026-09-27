"""
Applicability Domain checking for Maestri Flash Point Model.

The AD is defined by:
1. Features within training range
2. Mean distance to 5 nearest neighbors ≤ 95th percentile of training distances

Out-of-domain predictions are flagged and should not drive overall scores alone.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class ApplicabilityDomainResult:
    """Result of applicability domain check."""
    in_domain: bool
    distance: float
    threshold: float
    k_neighbors: int = 5
    reason: str = ""


def compute_ad_threshold(training_features: np.ndarray, percentile: float = 95.0, k: int = 5) -> float:
    """
    Compute applicability domain threshold from training data.
    
    The threshold is the 95th percentile of mean k-NN distances in training set.
    
    Args:
        training_features: Training feature matrix (n_samples, n_features).
        percentile: Percentile for threshold (default 95).
        k: Number of neighbors (default 5).
        
    Returns:
        AD threshold value.
    """
    if len(training_features) == 0:
        return float('inf')
    
    if len(training_features) <= k:
        return float('inf')
    
    n_samples = len(training_features)
    distances = []
    
    for i in range(n_samples):
        dists = []
        for j in range(n_samples):
            if i != j:
                d = np.linalg.norm(training_features[i] - training_features[j])
                dists.append(d)
        dists.sort()
        mean_knn_dist = np.mean(dists[:k])
        distances.append(mean_knn_dist)
    
    return float(np.percentile(distances, percentile))


def check_applicability_domain(
    query_features: np.ndarray,
    training_features: np.ndarray,
    threshold: float,
    k: int = 5,
) -> ApplicabilityDomainResult:
    """
    Check if a query compound is within the applicability domain.
    
    Criteria:
    1. Features within training range (implicit via k-NN distance)
    2. Mean distance to k nearest neighbors ≤ threshold (95th percentile)
    
    Args:
        query_features: Feature vector for query compound.
        training_features: Training feature matrix (n_samples, n_features).
        threshold: AD threshold (95th percentile of training k-NN distances).
        k: Number of neighbors (default 5).
        
    Returns:
        ApplicabilityDomainResult with in_domain flag and distance info.
    """
    if len(training_features) == 0:
        return ApplicabilityDomainResult(
            in_domain=False,
            distance=float('inf'),
            threshold=threshold,
            k_neighbors=k,
            reason="No training data available for AD check",
        )
    
    if len(training_features) < k:
        k = len(training_features)
    
    distances = []
    for training_sample in training_features:
        d = np.linalg.norm(query_features - training_sample)
        distances.append(d)
    
    distances.sort()
    mean_knn_distance = float(np.mean(distances[:k]))
    
    in_domain = bool(mean_knn_distance <= threshold)
    
    reason = ""
    if not in_domain:
        ratio = mean_knn_distance / threshold if threshold > 0 else float('inf')
        reason = f"Mean {k}-NN distance ({mean_knn_distance:.3f}) exceeds threshold ({threshold:.3f}) by {ratio:.1f}x"
    
    return ApplicabilityDomainResult(
        in_domain=in_domain,
        distance=mean_knn_distance,
        threshold=float(threshold),
        k_neighbors=k,
        reason=reason,
    )
