"""
On-demand TCI SDS / catalog enrichment for DoSS (slim, no GHaz7 import).

Uses the curated CAS→product map from GHaz7:
  ``GHhaz6/GHaz7/quick-hazard-assessment-app/data/tci_catalog_by_cas.csv``
  (falls back to ``tci_catalog_runtime.csv``).

Fetches a single SDS PDF via the predictable TCI URL when possible, then
extracts NFPA + section-9 physchem with lightweight regex. Optionally scrapes
list prices from the product page HTML when exposed — never invents prices.

NFPA is only accepted when the SDS text literally mentions NFPA/HMIS
(avoids false positives from GHS H225 / RCRA F003).

Sigma-Aldrich: stub only (``sigma_stub.py``); Millipore API access pending.
Do NOT call unverified ``api.sigmaaldrich.com``.
"""

from __future__ import annotations

import csv
import re
import time
from pathlib import Path
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from packages.p2oasys_core.lookup import APP_DIR, GHAZ7_ROOT, normalize_cas

TCI_CATALOG_CANDIDATES = (
    GHAZ7_ROOT / "data" / "tci_catalog_runtime.csv",
    GHAZ7_ROOT / "data" / "tci_catalog_by_cas.csv",
    APP_DIR / "tci_catalog_by_cas.csv",
)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
_PRODUCT_RE = re.compile(r"^[A-Za-z][0-9]{4}$")

# Require literal NFPA/HMIS — bare H/F digits false-positive on GHS H225 / RCRA F003.
_NFPA_BLOCK_RE = re.compile(
    r"(?:NFPA(?:\s*704)?|HMIS).{0,80}?"
    r"(?:Health|H)\s*[:=]?\s*([0-4]).{0,80}?"
    r"(?:Flammability|Fire|F)\s*[:=]?\s*([0-4])",
    re.I | re.S,
)
_NFPA_HEALTH_RE = re.compile(
    r"(?:NFPA(?:\s*704)?|HMIS).{0,60}?Health(?:\s*(?:hazard|rating))?\s*[:=]?\s*([0-4])",
    re.I | re.S,
)
_NFPA_FIRE_RE = re.compile(
    r"(?:NFPA(?:\s*704)?|HMIS).{0,60}?(?:Flammability|Fire)(?:\s*(?:hazard|rating))?\s*[:=]?\s*([0-4])",
    re.I | re.S,
)
_NFPA_DIAMOND_RE = re.compile(
    r"(?:NFPA(?:\s*704)?|HMIS).{0,40}?([0-4])\s*[-/]\s*([0-4])\s*[-/]\s*([0-4])",
    re.I | re.S,
)
_GLOVE_LINE_RE = re.compile(
    r"(?:Hand\s*protection|Protective\s*gloves|Glove(?:s)?(?:\s*material)?)\s*[:\-]\s*([^\n]{3,120})",
    re.I,
)
_GLOVE_MATERIAL_RE = re.compile(
    r"\b(nitrile|butyl|viton|neoprene|PVC|PVA|latex|natural\s*rubber|silver\s*shield|barrier)\b",
    re.I,
)
_PRICE_RE = re.compile(
    r"(?:US\$|\$)\s*(\d+(?:,\d{3})*(?:\.\d{2})?)",
    re.I,
)
_SIZE_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(mg|g|kg|mL|ml|L)\b",
    re.I,
)

_last_request_at = 0.0
_MIN_INTERVAL_S = 3.0


def _throttle() -> None:
    global _last_request_at
    elapsed = time.monotonic() - _last_request_at
    wait = _MIN_INTERVAL_S - elapsed
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.monotonic()


def _http_get(url: str, *, accept: str = "*/*", timeout: float = 25.0) -> tuple[int, bytes, str]:
    _throttle()
    req = Request(
        url,
        headers={
            "User-Agent": _USER_AGENT,
            "Accept": accept,
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", 200) or 200
            ctype = (resp.headers.get("Content-Type") or "").lower()
            data = resp.read()
            return int(status), data, ctype
    except HTTPError as e:
        body = e.read() if hasattr(e, "read") else b""
        return int(e.code), body or b"", ""
    except (URLError, TimeoutError, OSError):
        return 0, b"", ""


def load_tci_catalog(path: Path | None = None) -> dict[str, list[dict[str, str]]]:
    """Return digits-CAS → list of {product_number, name, notes}."""
    candidates = [path] if path else list(TCI_CATALOG_CANDIDATES)
    by_cas: dict[str, list[dict[str, str]]] = {}
    for p in candidates:
        if not p or not Path(p).is_file():
            continue
        try:
            with open(p, newline="", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    cas = normalize_cas(row.get("cas") or row.get("CAS"))
                    prod = (
                        row.get("product_number")
                        or row.get("product")
                        or row.get("catalog_number")
                        or ""
                    ).strip().upper()
                    if not cas or not prod or not _PRODUCT_RE.match(prod):
                        continue
                    by_cas.setdefault(cas, []).append(
                        {
                            "product_number": prod,
                            "name": (row.get("name") or "").strip(),
                            "notes": (row.get("notes") or "").strip(),
                        }
                    )
            if by_cas:
                return by_cas
        except Exception:
            continue
    return by_cas


def sds_url(product: str, *, region: str = "US/en", country: str = "US", language: str = "EN") -> str:
    prod = product.strip().upper()
    filename = f"{prod}_{country.upper()}_{language.upper()}.pdf"
    return f"https://www.tcichemicals.com/{region.strip('/')}/sds/{quote(filename, safe='._-')}"


def product_page_url(product: str, *, region: str = "US/en") -> str:
    prod = product.strip().upper()
    return f"https://www.tcichemicals.com/{region.strip('/')}/p/{quote(prod, safe='')}"


def _local_sds_cache_pdf(cas: str, product: str | None = None) -> Path | None:
    """Prefer a previously cached TCI SDS under GHaz7 cache/SDS when live HTTP is blocked."""
    digits = normalize_cas(cas)
    if not digits:
        return None
    root = GHAZ7_ROOT / "cache" / "SDS" / digits / "TCI"
    if not root.is_dir():
        return None
    pdfs = sorted(root.rglob("original.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)
    if product:
        prod = product.upper()
        for p in pdfs:
            meta = p.parent / "metadata.json"
            try:
                if meta.is_file() and prod in meta.read_text(encoding="utf-8", errors="ignore"):
                    return p
            except Exception:
                pass
    return pdfs[0] if pdfs else None


def _pdf_to_text(pdf_bytes: bytes) -> str:
    """Best-effort PDF text extraction without hard dependency on GHaz7."""
    if not pdf_bytes or not pdf_bytes.startswith(b"%PDF"):
        return ""
    for mod_name in ("pypdf", "PyPDF2"):
        try:
            import importlib
            from io import BytesIO

            mod = importlib.import_module(mod_name)
            reader = mod.PdfReader(BytesIO(pdf_bytes))
            parts = []
            for page in reader.pages[:20]:
                try:
                    parts.append(page.extract_text() or "")
                except Exception:
                    continue
            text = "\n".join(parts)
            if text.strip():
                return text
        except Exception:
            continue
    try:
        raw = pdf_bytes.decode("latin-1", errors="ignore")
        chunks = re.findall(r"[\x20-\x7e\n\r\t]{4,}", raw)
        return "\n".join(chunks[:5000])
    except Exception:
        return ""


def _first_num_celsius(text: str | None) -> Optional[float]:
    if not text:
        return None
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*°\s*C", text, re.I)
    if m:
        return float(m.group(1))
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*C\b", text, re.I)
    if m:
        return float(m.group(1))
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*°\s*F", text, re.I)
    if m:
        return (float(m.group(1)) - 32.0) * 5.0 / 9.0
    m = re.search(r"(-?\d+(?:\.\d+)?)", text)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


def _parse_density_g_l(text: str | None) -> Optional[float]:
    if not text:
        return None
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*(g\s*/\s*mL|g\s*/\s*cm3|g\s*cm-3|g/mL|g/cm3)", text, re.I)
    if m:
        return float(m.group(1)) * 1000.0
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*(g\s*/\s*L|g/L)", text, re.I)
    if m:
        return float(m.group(1))
    m = re.search(r"(-?\d+(?:\.\d+)?)", text)
    if m:
        v = float(m.group(1))
        if 0.1 < v < 5:
            return v * 1000.0
        return v
    return None


def parse_sds_fields(text: str) -> dict[str, Any]:
    """Extract NFPA (only if NFPA/HMIS present), gloves, and §9 physchem from SDS text."""
    out: dict[str, Any] = {}
    if not text:
        return out

    # NFPA only when the SDS literally mentions NFPA/HMIS (avoid H225/F003).
    if re.search(r"\b(?:NFPA|HMIS)\b", text, re.I):
        dm = _NFPA_DIAMOND_RE.search(text)
        if dm:
            out["nfpa_health"] = dm.group(1)
            out["nfpa_flame"] = dm.group(2)
        nm = _NFPA_BLOCK_RE.search(text)
        if nm:
            out.setdefault("nfpa_health", nm.group(1))
            out.setdefault("nfpa_flame", nm.group(2))
        if "nfpa_health" not in out:
            hm = _NFPA_HEALTH_RE.search(text)
            if hm:
                out["nfpa_health"] = hm.group(1)
        if "nfpa_flame" not in out:
            fm = _NFPA_FIRE_RE.search(text)
            if fm:
                out["nfpa_flame"] = fm.group(1)

    gm = _GLOVE_LINE_RE.search(text)
    if gm:
        raw = gm.group(1).strip()
        out["glove_raw"] = raw
        mats = _GLOVE_MATERIAL_RE.findall(raw)
        if mats:
            norm = []
            for m in mats:
                m2 = re.sub(r"\s+", " ", m.strip())
                if m2.lower() in ("pvc", "pva"):
                    norm.append(m2.upper())
                else:
                    norm.append(m2.title())
            seen: set[str] = set()
            uniq = []
            for x in norm:
                k = x.lower()
                if k not in seen:
                    seen.add(k)
                    uniq.append(x)
            out["glove_type"] = "/".join(uniq)
        elif re.search(r"impervious|protective\s*gloves", raw, re.I):
            # Generic SDS wording — caller should prefer curated GLOVE_MAP for material.
            out["glove_type"] = "Impervious gloves"

    def _section9_value(label: str) -> Optional[str]:
        m = re.search(rf"{label}\s*[:\-]\s*([^\n]{{3,120}})", text, re.I)
        return m.group(1).strip() if m else None

    bp = _section9_value(r"Boiling\s*point(?:\s*/\s*boiling\s*range)?")
    mp = _section9_value(r"Melting\s*point(?:\s*/\s*freezing\s*point)?")
    fp = _section9_value(r"Flash\s*point")
    dens = _section9_value(r"(?:Relative\s*)?Density") or _section9_value(r"Relative\s*density")
    vp = _section9_value(r"Vapor\s*pressure")
    visc = _section9_value(r"Viscosity")
    sol = _section9_value(r"Water\s*solubility") or _section9_value(r"Solubility")

    bp_n = _first_num_celsius(bp)
    mp_n = _first_num_celsius(mp)
    fp_n = _first_num_celsius(fp)
    if bp_n is not None:
        out["boiling_point_c"] = bp_n
    if mp_n is not None:
        out["melting_point_c"] = mp_n
    if fp_n is not None:
        out["flash_point_c"] = fp_n
    dens_n = _parse_density_g_l(dens)
    if dens_n is not None:
        out["density_g_l"] = dens_n
    if vp:
        m = re.search(r"(-?\d+(?:\.\d+)?)", vp)
        if m:
            out["vapor_pressure_mmhg"] = float(m.group(1))
    if visc:
        m = re.search(r"(-?\d+(?:\.\d+)?)", visc)
        if m:
            out["viscosity_cp"] = float(m.group(1))
    if sol:
        out["water_solubility_raw"] = sol

    return out


def parse_prices_from_html(html: str) -> dict[str, Any]:
    """Best-effort lab-scale $/g from TCI product page HTML. Never invents values."""
    if not html:
        return {}
    cleaned = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    cleaned = re.sub(r"<style[\s\S]*?</style>", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)

    candidates: list[tuple[float, float, str]] = []
    for m in _PRICE_RE.finditer(cleaned):
        try:
            price = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        if price <= 0 or price > 1_000_000:
            continue
        window = cleaned[max(0, m.start() - 80) : m.end() + 80]
        sm = _SIZE_RE.search(window)
        if not sm:
            continue
        amount = float(sm.group(1))
        unit = sm.group(2).lower()
        if amount <= 0:
            continue
        if unit == "mg":
            grams = amount / 1000.0
        elif unit == "g":
            grams = amount
        elif unit == "kg":
            grams = amount * 1000.0
        elif unit in ("ml", "l"):
            continue
        else:
            continue
        if grams <= 0:
            continue
        per_g = price / grams
        candidates.append((per_g, price, f"{amount}{unit} @ ${price:.2f}"))

    if not candidates:
        return {}
    candidates.sort(key=lambda x: x[1])
    per_g, price, note = candidates[0]
    return {
        "lab_cost_per_g": round(per_g, 4),
        "lab_cost_note": note,
    }


def enrich_from_tci(cas: str, *, fetch_pricing: bool = True) -> dict[str, Any]:
    """
    On-demand TCI enrich for one CAS.

    Tries live SDS URL first; on 403/HTML falls back to GHaz7 local SDS cache.
    """
    result: dict[str, Any] = {
        "ok": False,
        "sources": {},
        "error": None,
        "product_number": None,
        "sds_url": None,
    }
    catalog = load_tci_catalog()
    key = normalize_cas(cas)
    entries = catalog.get(key) or []
    product = entries[0]["product_number"] if entries else None
    result["product_number"] = product
    if product:
        result["sds_url"] = sds_url(product)

    pdf_bytes: bytes | None = None
    pdf_source = None

    if product:
        status, body, ctype = _http_get(result["sds_url"], accept="application/pdf,*/*;q=0.8")
        if status == 200 and body.startswith(b"%PDF"):
            pdf_bytes = body
            pdf_source = "tci_sds_live"
        else:
            result["error"] = f"sds_fetch_failed status={status} ctype={ctype[:40] if ctype else ''}"

    if pdf_bytes is None:
        local = _local_sds_cache_pdf(cas, product)
        if local and local.is_file():
            pdf_bytes = local.read_bytes()
            pdf_source = "tci_sds_cache"
            result["error"] = None
            result["sds_cache_path"] = str(local)

    if pdf_bytes and pdf_bytes.startswith(b"%PDF"):
        text = _pdf_to_text(pdf_bytes)
        fields = parse_sds_fields(text)
        result.update(fields)
        for k in (
            "nfpa_health",
            "nfpa_flame",
            "boiling_point_c",
            "melting_point_c",
            "flash_point_c",
            "density_g_l",
            "vapor_pressure_mmhg",
            "viscosity_cp",
            "water_solubility_raw",
            "glove_type",
            "glove_raw",
        ):
            if k in fields:
                result["sources"][k] = pdf_source
        result["ok"] = True
    elif not entries:
        result["error"] = "no_tci_catalog_hit"

    if fetch_pricing and product:
        try:
            p_status, p_body, _ = _http_get(
                product_page_url(product),
                accept="text/html,application/xhtml+xml",
            )
            if p_status == 200 and p_body:
                html = p_body.decode("utf-8", errors="ignore")
                prices = parse_prices_from_html(html)
                if prices.get("lab_cost_per_g") is not None:
                    result["lab_cost_per_g"] = prices["lab_cost_per_g"]
                    result["lab_cost_note"] = prices.get("lab_cost_note")
                    result["sources"]["lab_cost_per_g"] = "tci_product_page"
                    result["ok"] = True
        except Exception as exc:
            result.setdefault("pricing_error", str(exc))

    return result
