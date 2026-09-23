"""
PubChem PUG REST API client for fetching compound data.

Retrieves identity, physicochemical properties, and hazard information.

Implements NCBI PubChem Dynamic Request Throttling compliance:
  https://pubchem.ncbi.nlm.nih.gov/docs/dynamic-request-throttling

Key behaviors:
  - Process-wide rate limiting (default 0.35s between requests; env PUBCHEM_MIN_INTERVAL_S)
  - Exponential backoff with jitter on 429/503/5xx
  - Honors Retry-After header when present
  - Disk cache under data/cache/pubchem/ to reduce redundant fetches
  - Clear PubChemThrottledError for UI handling
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

PUBCHEM_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
PUBCHEM_VIEW_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug_view"
PUBCHEM_COMPOUND_URL = "https://pubchem.ncbi.nlm.nih.gov/compound"

REQUEST_TIMEOUT = 45
RETRYABLE_STATUS = {429, 500, 502, 503, 504}

_MIN_INTERVAL_S = float(os.environ.get("PUBCHEM_MIN_INTERVAL_S", "0.35"))
_MAX_RETRIES = int(os.environ.get("PUBCHEM_MAX_RETRIES", "5"))
_BASE_DELAY = 1.5
_MAX_DELAY = 60.0
_JITTER_FACTOR = 0.25

_last_request_lock = threading.Lock()
_last_request_at = 0.0

_CACHE_DIR: Path | None = None


def _get_cache_dir() -> Path:
    """Return cache directory, creating if needed."""
    global _CACHE_DIR
    if _CACHE_DIR is not None:
        return _CACHE_DIR
    env_cache = os.environ.get("PUBCHEM_CACHE_DIR")
    if env_cache:
        _CACHE_DIR = Path(env_cache)
    else:
        repo_root = Path(__file__).resolve().parents[2]
        _CACHE_DIR = repo_root / "data" / "cache" / "pubchem"
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR


def _cache_key(url: str) -> str:
    """Generate cache key from URL."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]


def _read_cache(url: str) -> Optional[Dict[str, Any]]:
    """Read cached response if available and not expired."""
    try:
        cache_dir = _get_cache_dir()
        key = _cache_key(url)
        cache_file = cache_dir / f"{key}.json"
        if not cache_file.is_file():
            return None
        stat = cache_file.stat()
        max_age = float(os.environ.get("PUBCHEM_CACHE_MAX_AGE_S", "86400"))
        if time.time() - stat.st_mtime > max_age:
            return None
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        return data
    except Exception:
        return None


def _write_cache(url: str, data: Dict[str, Any]) -> None:
    """Write response to cache."""
    try:
        cache_dir = _get_cache_dir()
        key = _cache_key(url)
        cache_file = cache_dir / f"{key}.json"
        cache_file.write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        pass


class PubChemError(Exception):
    """Raised when PubChem API returns an error or compound not found."""

    pass


class PubChemThrottledError(PubChemError):
    """Raised when PubChem returns 429/503 throttling after retries exhausted.

    The UI should catch this and show "PubChem throttled — try later / use
    universe SQLite scores" rather than a cryptic error.
    """

    def __init__(self, message: str, retry_after: Optional[float] = None):
        super().__init__(message)
        self.retry_after = retry_after


class PubChemNotFoundError(PubChemError):
    """Raised when compound is not found in PubChem (HTTP 404)."""

    pass


def _throttle() -> None:
    """Enforce minimum interval between PubChem requests (process-wide)."""
    global _last_request_at
    with _last_request_lock:
        elapsed = time.monotonic() - _last_request_at
        wait = _MIN_INTERVAL_S - elapsed
        if wait > 0:
            time.sleep(wait)
        _last_request_at = time.monotonic()


def _compute_delay(attempt: int, retry_after: Optional[float] = None) -> float:
    """Compute backoff delay with jitter."""
    base = _BASE_DELAY * (2 ** attempt)
    jitter = base * _JITTER_FACTOR * random.random()
    delay = base + jitter
    if retry_after is not None:
        delay = max(delay, retry_after)
    return min(delay, _MAX_DELAY)


def _is_throttle_response(resp: requests.Response) -> bool:
    """Check if response indicates PubChem throttling."""
    if resp.status_code in (429, 503):
        return True
    text = resp.text.lower() if resp.text else ""
    if "serverbusy" in text or "too many requests" in text:
        return True
    return False


def _get_retry_after(resp: requests.Response) -> Optional[float]:
    """Extract Retry-After header value in seconds."""
    ra = resp.headers.get("Retry-After")
    if not ra:
        return None
    try:
        return float(ra)
    except ValueError:
        return None


def _get_with_retries(
    url: str,
    *,
    label: str,
    attempts: int | None = None,
    use_cache: bool = True,
) -> requests.Response:
    """GET with rate limiting, caching, and exponential backoff with jitter.

    Args:
        url: The URL to fetch
        label: Human-readable description for error messages
        attempts: Max retry attempts (default from PUBCHEM_MAX_RETRIES)
        use_cache: Whether to use disk cache (default True)

    Returns:
        requests.Response on success

    Raises:
        PubChemThrottledError: On 429/503 after retries exhausted
        PubChemNotFoundError: On 404
        PubChemError: On other failures
    """
    if attempts is None:
        attempts = _MAX_RETRIES

    if use_cache:
        cached = _read_cache(url)
        if cached is not None:
            fake_resp = requests.Response()
            fake_resp.status_code = 200
            fake_resp._content = json.dumps(cached).encode("utf-8")
            fake_resp.headers["X-Cache"] = "HIT"
            return fake_resp

    last_exc: Exception | None = None
    last_retry_after: Optional[float] = None

    for i in range(attempts):
        _throttle()
        try:
            resp = requests.get(url, timeout=REQUEST_TIMEOUT)

            if resp.status_code == 404:
                raise PubChemNotFoundError(f"{label}: compound not found (404)")

            if resp.status_code in RETRYABLE_STATUS:
                last_retry_after = _get_retry_after(resp)
                is_throttle = _is_throttle_response(resp)

                if i + 1 < attempts:
                    delay = _compute_delay(i, last_retry_after)
                    time.sleep(delay)
                    continue

                if is_throttle:
                    raise PubChemThrottledError(
                        f"{label}: PubChem throttled (HTTP {resp.status_code}) after {attempts} attempts. "
                        "The service is experiencing high volume. Try again later or use offline SQLite scores.",
                        retry_after=last_retry_after,
                    )
                resp.raise_for_status()

            resp.raise_for_status()

            if use_cache and resp.status_code == 200:
                try:
                    data = resp.json()
                    _write_cache(url, data)
                except Exception:
                    pass

            return resp

        except PubChemThrottledError:
            raise
        except PubChemNotFoundError:
            raise
        except PubChemError:
            raise
        except requests.RequestException as e:
            last_exc = e
            if i + 1 < attempts:
                delay = _compute_delay(i)
                time.sleep(delay)
                continue
            break

    raise PubChemError(f"{label}: {last_exc}")


def get_cid_by_cas(cas: str) -> Optional[int]:
    """Look up PubChem CID by CAS registry number.

    Returns:
        CID if found, None if not found

    Raises:
        PubChemThrottledError: On throttling after retries
        PubChemError: On other failures
    """
    url = f"{PUBCHEM_BASE}/compound/name/{cas}/cids/JSON"
    try:
        resp = _get_with_retries(url, label=f"CID lookup for CAS {cas}")
        cids = resp.json().get("IdentifierList", {}).get("CID", [])
        return cids[0] if cids else None
    except PubChemNotFoundError:
        return None


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
    resp = _get_with_retries(url, label=f"Properties for CID {cid}")
    data = resp.json()
    props = data.get("PropertyTable", {}).get("Properties", [{}])[0]
    return props


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
        label=f"View data for CID {cid}",
        attempts=_MAX_RETRIES + 1,
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

    Raises:
        PubChemThrottledError: On throttling after retries (UI should catch this)
        PubChemNotFoundError: Compound not found
        PubChemError: Other API failures
    """
    cid = get_cid_by_cas(cas)
    if cid is None:
        raise PubChemNotFoundError(f"Compound not found for CAS {cas}")

    basic_props = get_compound_properties(cid)

    exp_props: Dict[str, Any] = {}
    view_warning: Optional[str] = None
    try:
        view_data = get_compound_view_data(cid)
        exp_props = extract_experimental_properties(view_data)
    except PubChemThrottledError:
        raise
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


def clear_cache() -> int:
    """Clear all cached PubChem responses. Returns number of files removed."""
    try:
        cache_dir = _get_cache_dir()
        count = 0
        for f in cache_dir.glob("*.json"):
            try:
                f.unlink()
                count += 1
            except Exception:
                pass
        return count
    except Exception:
        return 0


def get_cache_stats() -> Dict[str, Any]:
    """Return cache statistics."""
    try:
        cache_dir = _get_cache_dir()
        files = list(cache_dir.glob("*.json"))
        total_size = sum(f.stat().st_size for f in files)
        return {
            "cache_dir": str(cache_dir),
            "file_count": len(files),
            "total_size_bytes": total_size,
            "min_interval_s": _MIN_INTERVAL_S,
            "max_retries": _MAX_RETRIES,
        }
    except Exception as e:
        return {"error": str(e)}
