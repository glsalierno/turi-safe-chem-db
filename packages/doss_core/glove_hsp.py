"""
HSP-based glove polymer compatibility screen for DoSS.

Uses RED = Ra/Ro against published glove-material Hansen spheres.
RED < 1  → solvent inside polymer sphere → likely to swell/dissolve that polymer
           → flag as incompatible glove material
RED > 1  → outside sphere → solvent should not dissolve that polymer
           → better barrier candidate (still not a breakthrough-time claim)

Polymer table: 1-hour breakthrough HSP fits from
https://pchem4all.com/2011/01/07/chemically-resistant-glove-selection/
(Williams; spheres fit from breakthrough data — document as HSP-predicted).

Never invents solvent HSP — caller must pass D/P/H from HSPiP (or other real source).
"""

from __future__ import annotations

import math
from typing import Any, Iterable

# name -> (D, P, H, Ro)  [MPa^0.5]
# Default: 20-minute breakthrough HSP spheres (splash / short contact).
# Alternate 1-hour set available as GLOVE_POLYMER_HSP_1HR for stricter screening.
# Source: https://pchem4all.com/2011/01/07/chemically-resistant-glove-selection/
GLOVE_POLYMER_HSP_20MIN: dict[str, tuple[float, float, float, float]] = {
    "Nitrile": (17.5, 7.3, 6.5, 5.1),
    "Butyl": (16.5, 1.0, 5.1, 5.0),
    "Natural rubber": (14.5, 7.3, 4.5, 11.0),
    "PVC": (16.1, 7.1, 5.9, 9.3),
    "PVA": (11.2, 12.4, 13.0, 12.1),
    "Polyethylene": (16.9, 3.3, 4.1, 8.1),
    "Viton": (10.9, 14.5, 3.1, 14.1),
    "Neoprene": (17.6, 2.5, 5.9, 6.2),
}
GLOVE_POLYMER_HSP_1HR: dict[str, tuple[float, float, float, float]] = {
    "Nitrile": (16.6, 9.1, 4.4, 10.0),
    "Butyl": (15.8, -2.1, 4.0, 8.2),  # P as published in that fit
    "Natural rubber": (15.6, 3.4, 9.1, 14.0),
    "PVC": (14.9, 11.1, 3.8, 13.2),
    "PVA": (15.3, 13.2, 13.5, 8.8),
    "Polyethylene": (17.1, 3.1, 5.2, 8.2),
    "Viton": (16.5, 8.1, 8.3, 6.6),
    "Neoprene": (19.0, 8.0, 0.0, 13.2),
}
GLOVE_POLYMER_HSP = GLOVE_POLYMER_HSP_20MIN

DEFAULT_POLYMERS = tuple(GLOVE_POLYMER_HSP.keys())


def hansen_ra(d1: float, p1: float, h1: float, d2: float, p2: float, h2: float) -> float:
    """Hansen distance Ra between two HSP points."""
    return math.sqrt(4.0 * (d1 - d2) ** 2 + (p1 - p2) ** 2 + (h1 - h2) ** 2)


def red_to_polymer(
    solvent_d: float,
    solvent_p: float,
    solvent_h: float,
    polymer: str,
) -> float | None:
    """RED of solvent vs named glove polymer; None if polymer unknown."""
    row = GLOVE_POLYMER_HSP.get(polymer)
    if not row:
        return None
    d, p, h, ro = row
    if ro <= 0:
        return None
    return hansen_ra(solvent_d, solvent_p, solvent_h, d, p, h) / ro


def classify_polymers(
    solvent_d: float,
    solvent_p: float,
    solvent_h: float,
    *,
    polymers: Iterable[str] | None = None,
    red_incompatible_max: float = 1.0,
) -> dict[str, Any]:
    """
    Split polymers into incompatible (RED < threshold) vs should-not-dissolve (RED >= threshold).
    """
    polys = list(polymers) if polymers is not None else list(DEFAULT_POLYMERS)
    incompatible: list[tuple[str, float]] = []
    should_not_dissolve: list[tuple[str, float]] = []
    for name in polys:
        red = red_to_polymer(solvent_d, solvent_p, solvent_h, name)
        if red is None:
            continue
        if red < red_incompatible_max:
            incompatible.append((name, red))
        else:
            should_not_dissolve.append((name, red))
    incompatible.sort(key=lambda x: x[1])
    should_not_dissolve.sort(key=lambda x: -x[1])  # highest RED first (most distant)
    return {
        "incompatible": incompatible,
        "should_not_dissolve": should_not_dissolve,
    }


def format_glove_hsp_flag(
    *,
    solvent_d: float | None,
    solvent_p: float | None,
    solvent_h: float | None,
    known_glove: str | None = None,
) -> str | None:
    """
    Build Glove Type text.

    If known_glove is a real material (not Unknown/empty/Impervious), keep it and
    optionally append a short HSP note.

    If unknown, return:
      Unknown; incompatible with X, Y, Z; according to HSPiP solvent should not dissolve U, V, W
    """
    if solvent_d is None or solvent_p is None or solvent_h is None:
        return None
    try:
        d, p, h = float(solvent_d), float(solvent_p), float(solvent_h)
    except (TypeError, ValueError):
        return None

    classified = classify_polymers(d, p, h)
    bad = [n for n, _ in classified["incompatible"]]
    good = [n for n, _ in classified["should_not_dissolve"]]

    known = (known_glove or "").strip()
    known_l = known.lower()
    is_unknown = (
        not known
        or known_l in {"unknown", "-", "impervious gloves", "protective gloves"}
        or known.startswith("needs_")
    )

    if is_unknown:
        parts = ["Unknown"]
        if bad:
            parts.append("incompatible with " + ", ".join(bad))
        if good:
            parts.append(
                "according to HSPiP solvent should not dissolve " + ", ".join(good)
            )
        if len(parts) == 1:
            return "Unknown"
        return "; ".join(parts)

    # Known material from map/SDS — keep primary, add HSP caution if that material is incompatible
    note_bits = []
    if known in bad or any(known.lower() == b.lower() for b in bad):
        note_bits.append(f"HSP warns incompatible with {known}")
    elif bad:
        note_bits.append("HSP also incompatible with " + ", ".join(bad[:4]))
    if not note_bits:
        return known
    return f"{known} ({'; '.join(note_bits)})"


def glove_hsp_details(
    solvent_d: float,
    solvent_p: float,
    solvent_h: float,
) -> list[dict[str, Any]]:
    """Per-polymer RED table for sidebar/debug."""
    rows = []
    for name, (d, p, h, ro) in GLOVE_POLYMER_HSP.items():
        ra = hansen_ra(solvent_d, solvent_p, solvent_h, d, p, h)
        red = ra / ro if ro else None
        rows.append(
            {
                "polymer": name,
                "D": d,
                "P": p,
                "H": h,
                "Ro": ro,
                "Ra": round(ra, 3),
                "RED": round(red, 3) if red is not None else None,
                "flag": "incompatible" if red is not None and red < 1.0 else "should_not_dissolve",
            }
        )
    rows.sort(key=lambda r: (r["RED"] is None, r["RED"] if r["RED"] is not None else 99))
    return rows
