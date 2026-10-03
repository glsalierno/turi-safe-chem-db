"""
IUCLID 6 dossier access for turi-safe-chem-db.

This package provides offline parsing of ECHA REACH Study Results dossiers
(.i6z format) and extraction of typed toxicological and physicochemical
endpoints for use with the P2OASys scorer.

Public API:
    get_status() -> dict           # Check IUCLID configuration status
    lookup_cas(cas: str) -> list   # Get all endpoints for a CAS number
    get_extra_sources(cas: str)    # Get P2OASys extra_sources format
    is_enabled() -> bool           # Check if IUCLID is configured

Environment Variables:
    IUCLID_ENABLED          - Enable/disable (default: auto)
    IUCLID_DOSSIER_SOURCE   - Path to extracted dossiers or bulk .zip
    IUCLID_DOSSIER_INDEX    - Path to dossier_info xlsx or prebuilt index
    IUCLID_FORMAT_DIR       - Path to IUCLID format pack (for phrase labels)
    IUCLID_CACHE_DIR        - Cache location (default: user data dir)

    Legacy names (supported as aliases):
    OFFLINE_LOCAL_ARCHIVE   - Alias for IUCLID_DOSSIER_SOURCE
    OFFLINE_DOSSIER_INFO_XLSX - Alias for IUCLID_DOSSIER_INDEX
"""

from packages.iuclid_core.config import get_config, is_enabled, get_status
from packages.iuclid_core.extractor import (
    extract_dossier,
    extract_endpoints_for_cas,
    EndpointRecord,
)
from packages.iuclid_core.phrase_mapper import PhraseMapper, get_phrase_mapper
from packages.iuclid_core.cache import (
    IUCLIDCache,
    get_cache,
    build_cache_for_cas_list,
)

__all__ = [
    "get_config",
    "is_enabled",
    "get_status",
    "extract_dossier",
    "extract_endpoints_for_cas",
    "EndpointRecord",
    "PhraseMapper",
    "get_phrase_mapper",
    "IUCLIDCache",
    "get_cache",
    "build_cache_for_cas_list",
]


def lookup_cas(cas: str) -> list[dict]:
    """
    Look up all extracted endpoints for a CAS number.
    
    Returns a list of endpoint dicts with keys like:
        dossier_uuid, subtype, endpoint, value, unit, species, route,
        reliability, key_result, etc.
    
    Returns empty list if IUCLID is not configured.
    """
    if not is_enabled():
        return []
    
    cache = get_cache()
    if cache is not None:
        cached = cache.get_endpoints_for_cas(cas)
        if cached:
            return cached
    
    return extract_endpoints_for_cas(cas)


def get_extra_sources(cas: str) -> dict | None:
    """
    Get P2OASys extra_sources format for a CAS number.
    
    Returns a dict compatible with hazard_for_p2oasys.merge_extra_sources:
        {
            "toxicities": [...],
            "hazard_metrics": {...},
            "source_info": {...}
        }
    
    Returns None if IUCLID is not configured or no data found.
    """
    if not is_enabled():
        return None
    
    endpoints = lookup_cas(cas)
    if not endpoints:
        return None
    
    from packages.iuclid_core.bridge import endpoints_to_extra_sources
    return endpoints_to_extra_sources(endpoints, cas)
