"""
Data source adapters for auto_p2oasys.

Each adapter module provides functions to gather Evidence records from
a specific data source (PubChem, CAMEO, lookup tables, SDS, predictions).
"""

from . import pubchem
from . import cameo
from . import lookup_tables
from . import sds
from . import predictions

__all__ = [
    "pubchem",
    "cameo",
    "lookup_tables",
    "sds",
    "predictions",
]
