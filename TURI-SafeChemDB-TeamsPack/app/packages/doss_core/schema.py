"""
DoSS (Database of Safer Solvents) schema definition.

Matches TURI DoSS.xlsx sheet 'DoSS original datapoints' column structure,
plus companion P2OASys Source for provenance.
"""

from typing import Dict, Any, List

DOSS_COLUMNS: List[str] = [
    "P2OASys",
    "P2OASys Source",
    "Solvent Name",
    "CAS",
    "D",
    "P",
    "H",
    "NFPA Health",
    "NFPA Flame",
    "GHS Hazards",
    "Glove Type",
    "SDS Link",
    "Lab Scale Cost Est. ($/kg)",
    "Bulk Cost Est. ($/kg)",
    "NFPA Source",
    "Melting Point (C)",
    "Boiling Point (C)",
    "Molecular Weight",
    "Density (g/L)",
    "Molar Volume",
    "Viscosity (cP)",
    "Refractive Index",
    "Vapor Pressure (mmHg)",
    "Flash Point (C)",
    "Water Solubility (g/L)",
    "RER (HSP)",
    "Formula",
]

HSP_PLACEHOLDER = "needs_HSPiP"
EMPTY_VALUE = "-"

def empty_row() -> Dict[str, Any]:
    """Return a row dict with all DoSS columns set to empty placeholder."""
    return {col: EMPTY_VALUE for col in DOSS_COLUMNS}


def coverage_report(row: Dict[str, Any]) -> Dict[str, bool]:
    """
    Generate coverage report showing which columns have actual data vs empty/placeholder.
    Returns dict of column_name -> is_filled (True if has real data).
    """
    report = {}
    for col in DOSS_COLUMNS:
        value = row.get(col, EMPTY_VALUE)
        is_filled = (
            value is not None
            and value != EMPTY_VALUE
            and value != ""
            and value != HSP_PLACEHOLDER
        )
        report[col] = is_filled
    return report


def format_row_for_csv(row: Dict[str, Any]) -> Dict[str, str]:
    """
    Format a row for CSV export, ensuring all values are strings
    and columns are in correct order. Internal keys are omitted.
    """
    formatted = {}
    for col in DOSS_COLUMNS:
        value = row.get(col, EMPTY_VALUE)
        if value is None:
            formatted[col] = EMPTY_VALUE
        else:
            formatted[col] = str(value)
    return formatted
