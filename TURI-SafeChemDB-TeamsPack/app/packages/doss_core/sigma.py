"""
Sigma-Aldrich / MilliporeSigma pricing & SDS hook (STUB ONLY).

Millipore commercial API access is pending. Do NOT call unverified
``api.sigmaaldrich.com`` from this app.

When credentials / a supported SDK are available, implement:
  - CAS → catalog number resolution
  - SDS PDF retrieval
  - Lab / bulk list-price extraction

Until then, callers should leave Lab/Bulk cost columns as ``-``.
"""

from __future__ import annotations

from typing import Any


def enrich_from_sigma(cas: str) -> dict[str, Any]:
    """Stub: always returns unavailable. Millipore access pending."""
    return {
        "ok": False,
        "error": "sigma_stub_millipore_access_pending",
        "lab_cost_per_g": None,
        "bulk_cost_per_lb": None,
        "nfpa_health": None,
        "nfpa_flame": None,
        "sds_url": None,
        "note": (
            "Sigma-Aldrich/MilliporeSigma integration is stubbed. "
            "Do not call api.sigmaaldrich.com until access is verified."
        ),
    }
