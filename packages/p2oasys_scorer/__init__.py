"""
P2OASys Hazard Score Calculator Package.

Ported from GHaz7/GHaz8 P2OASys auto-scorer engine.
Version: p2oasys_scorer_v6.6_site_top2

This package provides the TURI P2OASys hazard scoring matrix loader and scorer
functions for chemical hazard assessment.

Usage:
    from packages.p2oasys_scorer import (
        load_p2oasys_matrix,
        compute_p2oasys_scores,
        compute_p2oasys_scores_with_trace,
        SCORER_VERSION,
    )

    matrix = load_p2oasys_matrix(matrix_path)
    scores = compute_p2oasys_scores(hazard_data, matrix)
"""

from .utils.p2oasys_scorer import (
    SCORER_VERSION,
    STATUS_SCORED,
    STATUS_NO_DATA,
    STATUS_NOT_ASSESSED,
    STATUS_PREDICTED_ONLY,
    STATUS_CONFLICTING,
    STATUS_SOURCE_UNAVAILABLE,
    DEFAULT_MATRIX_PATH,
    load_p2oasys_matrix,
    compute_p2oasys_scores,
    compute_p2oasys_scores_with_trace,
    mean_of_top_two_highest,
    matrix_fingerprint,
    parse_measured_value,
    mgm3_to_ppm,
    print_p2oasys_summary,
)

from .utils.p2oasys_ph import (
    estimate_ph_for_hazard,
    apply_ph_rule,
    score_ph_units,
)

from . import config

__version__ = "0.1.0"
__all__ = [
    # Version
    "SCORER_VERSION",
    "__version__",
    # Status constants
    "STATUS_SCORED",
    "STATUS_NO_DATA",
    "STATUS_NOT_ASSESSED",
    "STATUS_PREDICTED_ONLY",
    "STATUS_CONFLICTING",
    "STATUS_SOURCE_UNAVAILABLE",
    # Core functions
    "DEFAULT_MATRIX_PATH",
    "load_p2oasys_matrix",
    "compute_p2oasys_scores",
    "compute_p2oasys_scores_with_trace",
    "mean_of_top_two_highest",
    "matrix_fingerprint",
    "parse_measured_value",
    "mgm3_to_ppm",
    "print_p2oasys_summary",
    # pH functions
    "estimate_ph_for_hazard",
    "apply_ph_rule",
    "score_ph_units",
    # Config
    "config",
]
