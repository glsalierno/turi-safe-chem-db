"""
Gap-fill layer for auto_p2oasys.

Applies prediction/gap-fill strategies for the 34 auto subcategories
when measured data is unavailable. Follows P2OASys OR-of-pathways rule:
try pathways in order, measured before predicted, stop at first reliable one.
"""

from .layer import GapFillLayer, GapFillResult

__all__ = ["GapFillLayer", "GapFillResult"]
