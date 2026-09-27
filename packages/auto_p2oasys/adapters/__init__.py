"""
Data source adapters for auto_p2oasys.

Each adapter module provides functions to gather Evidence records from
a specific data source (PubChem, CAMEO, lookup tables, SDS, predictions, IUCLID).

IUCLID Attribution Requirement:
    Any result derived from IUCLID data MUST display:
    "Source: ECHA REACH Study Results (IUCLID), European Chemicals Agency"
"""

from . import pubchem
from . import cameo
from . import lookup_tables
from . import sds
from . import predictions
from . import iuclid

__all__ = [
    "pubchem",
    "cameo",
    "lookup_tables",
    "sds",
    "predictions",
    "iuclid",
]
