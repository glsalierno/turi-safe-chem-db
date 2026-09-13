"""
PubChem PUG REST API client for fetching compound data.

Retrieves identity, physicochemical properties, and hazard information.
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional

import requests

PUBCHEM_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
PUBCHEM_VIEW_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug_view"
PUBCHEM_COMPOUND_URL = "https://pubchem.ncbi.nlm.nih.gov/compound"

REQUEST_TIMEOUT = 45
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class PubChemError(Exception):
    """Raised when PubChem API returns an error or compound not found."""

    pass


def _get_with_retries(
    url: str,
    *,
    label: str,
    attempts: int = 4,
    base_delay: float = 1.5,
) -> requests.Response:
    """GET with backoff on transient PubChem errors (ServerBusy / 503 / 429)."""
    last_exc: Exception | None = None
    for i in range(attempts):
        try:
            resp = requests.get(url, timeout=REQUEST_TIMEOUT)
            if resp.status_code in RETRYABLE_STATUS:
                last_exc = requests.HTTPError(
                    f"{resp.status_code} Server Error for url: {url}",
                    response=resp,
                )
                # honor Retry-After when present
                delay = base_delay * (2**i)
                ra = resp.headers.get("Retry-After")
                if ra:
                    try:
                        delay = max(delay, float(ra))
                    except ValueError:
                        pass
                if i + 1 < attempts:
                    time.sleep(min(delay, 20.0))
                    continue
                resp.raise_for_status()
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            last_exc = e
            if i + 1 < attempts:
                time.sleep(min(base_delay * (2**i), 20.0))
                continue
            break
    raise PubChemError(f"{label}: {last_exc}")


def get_cid_by_cas(cas: str) -> Optional[int]:
    """Look up PubChem CID by CAS registry number."""
    url = f"{PUBCHEM_BASE}/compound/name/{cas}/cids/JSON"
    last_exc: Exception | None = None
    for i in range(4):
        try:
            resp = requests.get(url, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 404:
                return None
            if resp.status_code in RETRYABLE_STATUS:
                last_exc = requests.HTTPError(
                    f"{resp.status_code} for url: {url}", response=resp
                )
                time.sleep(min(1.5 * (2**i), 20.0))
                continue
            resp.raise_for_status()
            cids = resp.json().get("IdentifierList", {}).get("CID", [])
            return cids[0] if cids else None
        except requests.RequestException as e:
            last_exc = e
            time.sleep(min(1.5 * (2**i), 20.0))
    raise PubChemError(f"Failed to lookup CAS {cas}: {last_exc}")


def get_compound_properties(cid: int) -> Dict[str, Any]:
    """Fetch basic compound properties from PubChem."""
    properties = [
        "MolecularFormula",
        "MolecularWeight",
        "IUPACName",
        "Title",
        "CanonicalSMILES",
        "ConnectivitySMILES",
        "IsomericSMILES",
    ]
    url = f"{PUBCHEM_BASE}/compound/cid/{cid}/property/{','.join(properties)}/JSON"
    try:
        resp = _get_with_retries(url, label=f"Failed to fetch properties for CID {cid}")
        data = resp.json()
        props = data.get("PropertyTable", {}).get("Properties", [{}])[0]
        return props
    except PubChemError:
        raise
    except requests.RequestException as e:
        raise PubChemError(f"Failed to fetch properties for CID {cid}: {e}") from e




def get_smiles_for_cas(cas: str) -> Optional[str]:
    """PubChem Canonical/Isomeric SMILES for a CAS. None if unknown. Never invents."""
    cid = get_cid_by_cas(cas)
    if cid is None:
        return None
    props = get_compound_properties(cid)
    smiles = (
        props.get("CanonicalSMILES")
        or props.get("IsomericSMILES")
        or props.get("ConnectivitySMILES")
        or ""
    )
    smiles = str(smiles).strip()
    return smiles or None


def get_compound_view_data(cid: int) -> Dict[str, Any]:
    """Fetch extended compound data from PUG View API (retries on ServerBusy)."""
    url = f"{PUBCHEM_VIEW_BASE}/data/compound/{cid}/JSON"
    resp = _get_with_retries(
        url,
        label=f"Failed to fetch view data for CID {cid}",
        attempts=5,
        base_delay=2.0,
    )
    return resp.json()


def extract_experimental_properties(view_data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract experimental properties and hazards from PUG View response."""
    result: Dict[str, Any] = {}

    try:
        record = view_data.get("Record", {})
        sections = record.get("Section", [])

        for section in sections:
            heading = section.get("TOCHeading", "")

            if heading == "Chemical and Physical Properties":
                for subsec in section.get("Section", []):
                    sub_heading = subsec.get("TOCHeading", "")

                    if sub_heading == "Experimental Properties":
                        for prop_sec in subsec.get("Section", []):
                            prop_name = prop_sec.get("TOCHeading", "")
                            info_list = prop_sec.get("Information", [])

                            if info_list:
                                value = _extract_first_value(info_list)
                                if value is not None:
                                    result[prop_name] = value

                    elif sub_heading == "Computed Properties":
                        for prop_sec in subsec.get("Section", []):
                            prop_name = prop_sec.get("TOCHeading", "")
                            info_list = prop_sec.get("Information", [])

                            if prop_name == "Molecular Weight" and info_list:
                                value = _extract_first_value(info_list)
                                if value is not None:
                                    result["Molecular Weight"] = value

            elif heading == "Safety and Hazards":
                for subsec in section.get("Section", []):
                    sub_heading = subsec.get("TOCHeading", "")

                    if sub_heading == "Hazards Identification":
                        for hazard_sec in subsec.get("Section", []):
                            hazard_name = hazard_sec.get("TOCHeading", "")

                            if hazard_name == "GHS Classification":
                                result["GHS"] = _extract_ghs_hazards(hazard_sec)

                            elif hazard_name == "NFPA Hazard Classification":
                                nfpa = _extract_nfpa(hazard_sec)
                                result.update(nfpa)

    except (KeyError, IndexError, TypeError):
        pass

    return result


def _extract_first_value(info_list: List[Dict]) -> Optional[str]:
    """Extract the first string or numeric value from an Information list."""
    for info in info_list:
        value = info.get("Value", {})

        if "StringWithMarkup" in value:
            strings = value["StringWithMarkup"]
            if strings and "String" in strings[0]:
                return strings[0]["String"]

        if "Number" in value:
            nums = value["Number"]
            if nums:
                unit = value.get("Unit", "")
                return f"{nums[0]} {unit}".strip() if unit else str(nums[0])

    return None


def _extract_ghs_hazards(ghs_section: Dict) -> List[str]:
    """Extract GHS hazard codes from GHS Classification section."""
    hazards: List[str] = []

    for info in ghs_section.get("Information", []):
        value = info.get("Value", {})
        if "StringWithMarkup" in value:
            for item in value["StringWithMarkup"]:
                text = item.get("String", "")
                for part in re.findall(r"\bH\d{3}[A-Z]?\b", text):
                    if part not in hazards:
                        hazards.append(part)
                if text.startswith("H") and len(text) > 3 and text[1:4].isdigit():
                    code = text.split()[0].rstrip(":")
                    if code not in hazards:
                        hazards.append(code)

    return hazards


def _extract_nfpa(nfpa_section: Dict) -> Dict[str, str]:
    """Extract NFPA health and flammability ratings from PUG View.

    PubChem usually stores ratings as:
    - ``NFPA Health Rating`` / ``NFPA Fire Rating`` strings like ``1 - Materials...``
    - Diamond icon Markup ``Extra`` codes like ``1-3-0`` (H-F-R)
    - Occasionally numeric ``Value.Number`` fields
    """
    result: Dict[str, str] = {}

    def _first_digit(s: str) -> str | None:
        s = (s or "").strip()
        m = re.match(r"([0-4])\b", s)
        return m.group(1) if m else None

    for info in nfpa_section.get("Information", []):
        name = info.get("Name", "") or ""
        value = info.get("Value", {}) or {}

        if "Number" in value:
            num = value["Number"][0] if value["Number"] else None
            if num is not None:
                if "Health" in name:
                    result["NFPA Health"] = str(int(num))
                elif "Fire" in name or "Flammability" in name:
                    result["NFPA Flame"] = str(int(num))

        swm = value.get("StringWithMarkup") or []
        if swm:
            text = swm[0].get("String", "") if isinstance(swm[0], dict) else ""
            digit = _first_digit(text)
            # Diamond Extra: "1-3-0"
            for mk in swm[0].get("Markup", []) or []:
                extra = (mk.get("Extra") or "").strip()
                m = re.match(r"([0-4])-([0-4])-([0-4])", extra)
                if m:
                    result.setdefault("NFPA Health", m.group(1))
                    result.setdefault("NFPA Flame", m.group(2))
            if digit:
                if "Health" in name:
                    result["NFPA Health"] = digit
                elif "Fire" in name or "Flammability" in name:
                    result["NFPA Flame"] = digit

    return result


def parse_numeric_with_unit(
    value_str: str, _target_unit: Optional[str] = None
) -> Optional[float]:
    """
    Parse a numeric value from a string that may contain units.

    If the numeric token is immediately followed by °F / F (temperature unit),
    convert to Celsius. A °F appearing later in the string (e.g. density
    measured "at 68 °F") does NOT trigger conversion of the leading number.
    """
    if not value_str:
        return None

    s = str(value_str)
    match = re.search(r"[-+]?\d*\.?\d+", s)
    if not match:
        return None
    try:
        num = float(match.group())
    except ValueError:
        return None

    after = s[match.end() : match.end() + 16]
    if re.match(r"\s*°?\s*F\b", after, re.I) or re.match(
        r"\s*(?:deg(?:ree)?s?\s*)?F(?:ahrenheit)?\b", after, re.I
    ):
        return (num - 32.0) * 5.0 / 9.0

    return num


def fetch_compound_data(cas: str, name_hint: Optional[str] = None) -> Dict[str, Any]:
    """
    Fetch compound data for a CAS number.

    Basic identity always comes from PUG REST. PUG View (physchem / GHS / NFPA)
    is retried on ServerBusy; if it still fails, the row is built from identity
    alone and ``view_warning`` explains the partial result.
    """
    cid = get_cid_by_cas(cas)
    if cid is None:
        raise PubChemError(f"Compound not found for CAS {cas}")

    basic_props = get_compound_properties(cid)
    time.sleep(0.25)

    exp_props: Dict[str, Any] = {}
    view_warning: Optional[str] = None
    try:
        view_data = get_compound_view_data(cid)
        exp_props = extract_experimental_properties(view_data)
    except PubChemError as e:
        view_warning = str(e)

    name = name_hint or basic_props.get("Title") or basic_props.get("IUPACName", "")

    return {
        "cid": cid,
        "name": name,
        "cas": cas,
        "formula": basic_props.get("MolecularFormula", ""),
        "molecular_weight": basic_props.get("MolecularWeight"),
        "properties": exp_props,
        "ghs_hazards": exp_props.get("GHS", []),
        "nfpa_health": exp_props.get("NFPA Health"),
        "nfpa_flame": exp_props.get("NFPA Flame"),
        "pubchem_url": f"{PUBCHEM_COMPOUND_URL}/{cid}",
        "view_warning": view_warning,
        "smiles": (
            basic_props.get("CanonicalSMILES")
            or basic_props.get("IsomericSMILES")
            or basic_props.get("ConnectivitySMILES")
            or ""
        ),
    }
