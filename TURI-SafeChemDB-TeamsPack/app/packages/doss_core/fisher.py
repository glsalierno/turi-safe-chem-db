"""
On-demand Fisher Scientific SDS / catalog enrichment for DoSS.

Public endpoints only (no login):
  - SDS PDF:  https://www.fishersci.com/store/msds?partNumber=...&vendorId=VN00033897&countryCode=US&language=en
  - Product:  https://www.fishersci.com/shop/products/.../<slug>

Probe (2026-09-13): acetone/methanol/toluene SDS returned HTTP 200 application/pdf;
product pages expose promotional list prices without login (contract price needs Sign In).

Does NOT call api.sigmaaldrich.com. Prefer this module over Sigma stub for live SDS.
Avoid wiring into app.py from concurrent HSPiP edits — import on demand.
"""

from __future__ import annotations

import csv
import re
import time
from pathlib import Path
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

try:
    from packages.p2oasys_core.lookup import APP_DIR, normalize_cas
except Exception:  # standalone / box without p2oasys_lookup
    APP_DIR = Path(__file__).resolve().parent

    def normalize_cas(cas: str | None) -> str:
        if not cas:
            return ""
        return "".join(c for c in str(cas) if c.isdigit())

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# Seed map for solvents proven in the 2026-09-13 live probe.
# part_number feeds /store/msds; product_url is a known shop page with public list price.
_SEED: dict[str, dict[str, str]] = {
    # digits-CAS → catalog hints (priority-62 commons; extend via fisher_catalog_by_cas.csv)
    "67641": {
        "name": "Acetone",
        "part_number": "A181",
        "product_url": "https://www.fishersci.com/shop/products/acetone-certified-acs-fisher-chemical/A18-4",
        "density_g_ml": "0.791",
    },
    "67561": {
        "name": "Methanol",
        "part_number": "A412",
        "product_url": "https://www.fishersci.com/shop/products/methanol-certified-acs-fisher-chemical-8/A4124",
        "density_g_ml": "0.791",
    },
    "108883": {
        "name": "Toluene",
        "part_number": "T324",
        "product_url": "https://www.fishersci.com/shop/products/toluene-certified-acs-fisher-chemical-6/T3244",
        "density_g_ml": "0.867",
    },
    "64175": {
        "name": "Ethanol",
        "part_number": "A995",
        "product_url": "https://www.fishersci.com/shop/products/ethyl-alcohol-absolute-200-proof-acs-fisher-chemical/A995-4",
        "density_g_ml": "0.789",
    },
    "75058": {
        "name": "Acetonitrile",
        "part_number": "A998",
        "product_url": "https://www.fishersci.com/shop/products/acetonitrile-certified-acs-fisher-chemical/A998-4",
        "density_g_ml": "0.786",
    },
    "141786": {
        "name": "Ethyl Acetate",
        "part_number": "E145",
        "product_url": "https://www.fishersci.com/shop/products/ethyl-acetate-certified-acs-fisher-chemical/E145-4",
        "density_g_ml": "0.902",
    },
    "67630": {
        "name": "2-Propanol",
        "part_number": "A416",
        "product_url": "https://www.fishersci.com/shop/products/2-propanol-certified-acs-fisher-chemical/A416-4",
        "density_g_ml": "0.785",
    },
    "110543": {
        "name": "Hexanes",
        "part_number": "H292",
        "product_url": "https://www.fishersci.com/shop/products/hexanes-certified-acs-fisher-chemical/H292-4",
        "density_g_ml": "0.659",
    },
    "75092": {
        "name": "Dichloromethane",
        "part_number": "D37",
        "product_url": "https://www.fishersci.com/shop/products/dichloromethane-certified-acs-fisher-chemical/D37-4",
        "density_g_ml": "1.325",
    },
    "109999": {
        "name": "THF",
        "part_number": "T397",
        "product_url": "https://www.fishersci.com/shop/products/tetrahydrofuran-certified-acs-fisher-chemical/T397-4",
        "density_g_ml": "0.889",
    },
    "67685": {
        "name": "DMSO",
        "part_number": "D128",
        "product_url": "https://www.fishersci.com/shop/products/dimethyl-sulfoxide-certified-acs-fisher-chemical/D128-4",
        "density_g_ml": "1.100",
    },
}

_CATALOG_CANDIDATES = (
    APP_DIR / "fisher_catalog_by_cas.csv",
)

_DEFAULT_VENDOR_ID = "VN00033897"

# Fisher SDS NFPA table: Health / Flammability / Instability under an NFPA heading.
_NFPA_TABLE_RE = re.compile(
    r"\bNFPA\b.{0,120}?"
    r"Health.{0,80}?Flammability.{0,80}?(?:Instability|Reactivity).{0,80}?"
    r"([0-4])\s+([0-4])\s+([0-4])",
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
_GLOVE_LINE_RE = re.compile(
    r"(?:Hand\s*protection|Protective\s*gloves|Glove(?:s)?(?:\s*material)?|Skin\s*and\s*body\s*protection)\s*[:\-]?\s*([^\n]{3,160})",
    re.I,
)
_GLOVE_MATERIAL_RE = re.compile(
    r"\b(nitrile|butyl|viton|neoprene|PVC|PVA|latex|natural\s*rubber|silver\s*shield|barrier)\b",
    re.I,
)
_PRICE_RE = re.compile(r"(?:US\$|\$)\s*(\d+(?:,\d{3})*(?:\.\d{2})?)")
_SIZE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(mg|g|kg|mL|ml|L)\b", re.I)
_DENSITY_RE = re.compile(
    r"(?:Density\s*/\s*Specific\s*Gravity|Specific\s*Gravity|(?<!Vapor\s)(?<!Bulk\s)Density)\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?)",
    re.I,
)
_VAPOR_DENSITY_SKIP = re.compile(r"Vapor\s*Density|Bulk\s*Density", re.I)

_last_request_at = 0.0
_MIN_INTERVAL_S = 3.0


def _throttle() -> None:
    global _last_request_at
    elapsed = time.monotonic() - _last_request_at
    wait = _MIN_INTERVAL_S - elapsed
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.monotonic()


def _http_get(url: str, *, accept: str = "*/*", timeout: float = 30.0) -> tuple[int, bytes, str]:
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


def sds_url(part_number: str, *, vendor_id: str = _DEFAULT_VENDOR_ID) -> str:
    q = urlencode(
        {
            "partNumber": part_number.strip(),
            "productDescription": part_number.strip(),
            "vendorId": vendor_id,
            "countryCode": "US",
            "language": "en",
        }
    )
    return f"https://www.fishersci.com/store/msds?{q}"


def load_fisher_catalog(path: Path | None = None) -> dict[str, list[dict[str, str]]]:
    """Return digits-CAS → list of catalog dicts (seed + optional CSV)."""
    by_cas: dict[str, list[dict[str, str]]] = {
        k: [dict(v)] for k, v in _SEED.items()
    }
    candidates = [path] if path else list(_CATALOG_CANDIDATES)
    for p in candidates:
        if not p or not Path(p).is_file():
            continue
        try:
            with open(p, newline="", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    cas = normalize_cas(row.get("cas") or row.get("CAS"))
                    part = (row.get("part_number") or row.get("partNumber") or "").strip()
                    if not cas or not part:
                        continue
                    entry = {
                        "name": (row.get("name") or "").strip(),
                        "part_number": part,
                        "product_url": (row.get("product_url") or "").strip(),
                        "density_g_ml": (row.get("density_g_ml") or "").strip(),
                    }
                    by_cas.setdefault(cas, []).append(entry)
        except Exception:
            continue
    return by_cas


def _pdf_to_text(pdf_bytes: bytes) -> str:
    if not pdf_bytes or not pdf_bytes.startswith(b"%PDF"):
        return ""
    # Prefer poppler pdftotext when available (better for Fisher layout).
    try:
        import subprocess
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name
        try:
            proc = subprocess.run(
                ["pdftotext", "-layout", tmp_path, "-"],
                capture_output=True,
                timeout=30,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout:
                return proc.stdout.decode("utf-8", errors="ignore")
        finally:
            Path(tmp_path).unlink(missing_ok=True)
    except Exception:
        pass
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


def parse_sds_fields(text: str) -> dict[str, Any]:
    """Extract NFPA + glove hints from Fisher SDS text. NFPA only if NFPA/HMIS present."""
    out: dict[str, Any] = {}
    if not text:
        return out

    if re.search(r"\b(?:NFPA|HMIS)\b", text, re.I):
        tm = _NFPA_TABLE_RE.search(text)
        if tm:
            out["nfpa_health"] = tm.group(1)
            out["nfpa_flame"] = tm.group(2)
            out["nfpa_instability"] = tm.group(3)
        if "nfpa_health" not in out:
            hm = _NFPA_HEALTH_RE.search(text)
            if hm:
                out["nfpa_health"] = hm.group(1)
        if "nfpa_flame" not in out:
            fm = _NFPA_FIRE_RE.search(text)
            if fm:
                out["nfpa_flame"] = fm.group(1)

    gm = re.search(
        r"Skin\s*and\s*body\s*protection\s*[:\-]?\s*([^\n]{3,160})",
        text,
        re.I,
    ) or _GLOVE_LINE_RE.search(text)
    if gm:
        raw = gm.group(1).strip()
        # Ignore bare GHS pictogram phrases without material guidance.
        if re.search(r"Wear protective gloves/protective clothing", raw, re.I) and not re.search(
            r"Skin\s*and\s*body", gm.group(0), re.I
        ):
            gm2 = re.search(
                r"Skin\s*and\s*body\s*protection\s*[:\-]?\s*([^\n]{3,160})",
                text,
                re.I,
            )
            if gm2:
                gm = gm2
                raw = gm2.group(1).strip()
        out["glove_raw"] = raw
        mats = _GLOVE_MATERIAL_RE.findall(raw + "\n" + text[gm.start() : gm.start() + 400])
        if mats:
            norm = []
            seen: set[str] = set()
            for m in mats:
                m2 = re.sub(r"\s+", " ", m.strip())
                if m2.lower() in ("pvc", "pva"):
                    m2 = m2.upper()
                else:
                    m2 = m2.title()
                if m2.lower() not in seen:
                    seen.add(m2.lower())
                    norm.append(m2)
            out["glove_type"] = "/".join(norm)
        elif re.search(r"protective\s*gloves|appropriate\s*protective\s*gloves", raw, re.I):
            out["glove_type"] = "Impervious gloves"

    for dm in _DENSITY_RE.finditer(text):
        # Skip vapor/bulk density false positives by checking a short left context.
        left = text[max(0, dm.start() - 20) : dm.start()]
        if _VAPOR_DENSITY_SKIP.search(left + dm.group(0)[:40]):
            continue
        try:
            val = float(dm.group(1))
        except ValueError:
            continue
        # Liquid densities for solvents are typically 0.6–2.0 g/mL
        if 0.5 <= val <= 2.5:
            out["density_g_ml"] = val
            out["density_g_l"] = val * 1000.0
            break

    return out


def parse_prices_from_html(
    html: str, *, density_g_ml: float | None = None
) -> dict[str, Any]:
    """
    Best-effort lab-scale $/g from Fisher product HTML.

    Public promotional list prices are visible without login as::
      $445.50 $283.65 / Each Save $161.85
    where the second dollar amount is the promo unit price. Contract pricing
    ("Sign In or Register to check your price") is ignored. Never invents values.
    """
    if not html:
        return {}
    cleaned = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    cleaned = re.sub(r"<style[\s\S]*?</style>", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)

    candidates: list[tuple[float, float, str]] = []

    # Primary: "$list $promo / Each" optionally followed by "Save $diff"
    each_re = re.compile(
        r"(?:Catalog\s*No\.?\s*(?P<cat>[A-Za-z0-9\-]+).{0,160})?"
        r"\$(?P<list>\d+(?:,\d{3})*(?:\.\d{2})?)\s+"
        r"\$(?P<promo>\d+(?:,\d{3})*(?:\.\d{2})?)\s*/\s*Each"
        r"(?:\s*Save\s*\$[\d,.]+)?",
        re.I,
    )
    for m in each_re.finditer(cleaned):
        try:
            price = float(m.group("promo").replace(",", ""))
        except ValueError:
            continue
        # Size: look left for Quantity / pack size near this match
        window = cleaned[max(0, m.start() - 500) : m.end() + 40]
        sm = _SIZE_RE.search(window)
        if not sm:
            continue
        amount = float(sm.group(1))
        unit = sm.group(2).lower()
        grams = _amount_to_grams(amount, unit, density_g_ml)
        if not grams:
            continue
        cat = m.group("cat") or "?"
        note = f"{cat} {amount}{unit} @ ${price:.2f}/Each"
        candidates.append((price / grams, price, note))

    # Secondary: single "$X / Each" without strikethrough list
    if not candidates:
        each1 = re.compile(
            r"\$(?P<price>\d+(?:,\d{3})*(?:\.\d{2})?)\s*/\s*Each",
            re.I,
        )
        for m in each1.finditer(cleaned):
            # skip if preceded by "Save"
            left = cleaned[max(0, m.start() - 12) : m.start()]
            if re.search(r"Save\s*$", left, re.I):
                continue
            try:
                price = float(m.group("price").replace(",", ""))
            except ValueError:
                continue
            window = cleaned[max(0, m.start() - 500) : m.end() + 40]
            sm = _SIZE_RE.search(window)
            if not sm:
                continue
            amount = float(sm.group(1))
            unit = sm.group(2).lower()
            grams = _amount_to_grams(amount, unit, density_g_ml)
            if not grams:
                continue
            note = f"{amount}{unit} @ ${price:.2f}/Each"
            candidates.append((price / grams, price, note))

    if not candidates:
        dollars = []
        for m in _PRICE_RE.finditer(cleaned):
            left = cleaned[max(0, m.start() - 10) : m.start()]
            if re.search(r"Save\s*$", left, re.I):
                continue
            try:
                v = float(m.group(1).replace(",", ""))
            except ValueError:
                continue
            if 1 <= v <= 100000:
                dollars.append(v)
        if dollars:
            return {
                "list_price_samples_usd": sorted(set(dollars))[:8],
                "lab_cost_note": "list prices visible; size pairing failed",
            }
        return {}

    candidates.sort(key=lambda x: x[1])
    per_g, price, note = candidates[0]
    return {
        "lab_cost_per_g": round(per_g, 6),
        "lab_cost_note": note,
        "list_price_usd": price,
    }


def _amount_to_grams(
    amount: float, unit: str, density_g_ml: float | None
) -> float | None:
    unit = unit.lower()
    if amount <= 0:
        return None
    if unit == "mg":
        return amount / 1000.0
    if unit == "g":
        return amount
    if unit == "kg":
        return amount * 1000.0
    if unit in ("ml", "l"):
        if not density_g_ml or density_g_ml <= 0:
            return None
        ml = amount if unit == "ml" else amount * 1000.0
        return ml * density_g_ml
    return None


def enrich_from_fisher(cas: str, *, fetch_pricing: bool = True) -> dict[str, Any]:
    """On-demand Fisher enrich for one CAS using curated part numbers."""
    result: dict[str, Any] = {
        "ok": False,
        "sources": {},
        "error": None,
        "part_number": None,
        "sds_url": None,
        "vendor": "Fisher Scientific",
    }
    catalog = load_fisher_catalog()
    key = normalize_cas(cas)
    entries = catalog.get(key) or []
    entry = entries[0] if entries else None
    if not entry:
        result["error"] = "no_fisher_catalog_hit"
        return result

    part = entry.get("part_number") or ""
    result["part_number"] = part
    result["product_url"] = entry.get("product_url") or None
    result["sds_url"] = sds_url(part) if part else None

    pdf_bytes: bytes | None = None
    pdf_source = None
    if result["sds_url"]:
        status, body, ctype = _http_get(
            result["sds_url"], accept="application/pdf,*/*;q=0.8"
        )
        if status == 200 and body.startswith(b"%PDF"):
            pdf_bytes = body
            pdf_source = "fisher_sds_live"
        else:
            result["error"] = (
                f"sds_fetch_failed status={status} ctype={ctype[:40] if ctype else ''}"
            )

    density_g_ml: float | None = None
    if entry.get("density_g_ml"):
        try:
            density_g_ml = float(entry["density_g_ml"])
        except ValueError:
            density_g_ml = None

    if pdf_bytes and pdf_bytes.startswith(b"%PDF"):
        text = _pdf_to_text(pdf_bytes)
        fields = parse_sds_fields(text)
        result.update(fields)
        if fields.get("density_g_ml"):
            density_g_ml = float(fields["density_g_ml"])
        for k in (
            "nfpa_health",
            "nfpa_flame",
            "nfpa_instability",
            "density_g_ml",
            "density_g_l",
            "glove_type",
            "glove_raw",
        ):
            if k in fields:
                result["sources"][k] = pdf_source
        result["ok"] = True
        result["error"] = None

    if fetch_pricing and entry.get("product_url"):
        try:
            p_status, p_body, _ = _http_get(
                entry["product_url"],
                accept="text/html,application/xhtml+xml",
            )
            if p_status == 200 and p_body:
                html = p_body.decode("utf-8", errors="ignore")
                prices = parse_prices_from_html(html, density_g_ml=density_g_ml)
                if prices.get("lab_cost_per_g") is not None:
                    result["lab_cost_per_g"] = prices["lab_cost_per_g"]
                    result["lab_cost_note"] = prices.get("lab_cost_note")
                    result["list_price_usd"] = prices.get("list_price_usd")
                    result["sources"]["lab_cost_per_g"] = "fisher_product_page"
                    result["ok"] = True
                elif prices.get("list_price_samples_usd"):
                    result["list_price_samples_usd"] = prices["list_price_samples_usd"]
                    result["lab_cost_note"] = prices.get("lab_cost_note")
                    result["sources"]["list_price_samples_usd"] = "fisher_product_page"
                    result["ok"] = True
            else:
                result.setdefault(
                    "pricing_error", f"product_fetch_failed status={p_status}"
                )
        except Exception as exc:
            result.setdefault("pricing_error", str(exc))

    return result


if __name__ == "__main__":
    import json
    import sys

    cas = sys.argv[1] if len(sys.argv) > 1 else "67-64-1"
    print(json.dumps(enrich_from_fisher(cas), indent=2, default=str))
