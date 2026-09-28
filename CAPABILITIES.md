# CAPABILITIES — TURI Safe Chem DB

Capability status for external data sources and integrations.

## PubChem Bulk/FTP Index

**Status:** ✅ Implemented (PR #7)
**Test coverage:** 26 unit tests (all offline with synthetic fixtures)

### Files Indexed

| File | Purpose | Size | Required |
|------|---------|------|----------|
| `CID-Identifiers.tsv.gz` | CAS → CID (PRIMARY, official registry) | ~50 MB | Yes |
| `CID-Synonym-filtered.gz` | CAS → CID (FALLBACK, all synonyms) | ~600 MB | Yes |
| `CID-LCSS.xml.gz` | GHS, NFPA, flash point, vapor pressure, IARC | ~456 MB | Yes |
| `CID-SMILES.gz` | CID → SMILES | ~3.5 GB | Optional |
| `CID-Title.gz` | CID → compound name | ~2.5 GB | Optional |
| `CID-InChI-Key.gz` | CID → InChI key | ~4 GB | Optional |

**Total (core):** ~1.1 GB compressed + ~300 MB SQLite index
**Total (full):** ~11 GB compressed + ~2 GB SQLite index

### CAS → CID Resolution

199 of 1,228 expert CAS numbers map to multiple PubChem CIDs. Resolution rules:

1. **PRIMARY:** CID-Identifiers CAS rows (official registry, authoritative)
2. **FALLBACK:** CID-Synonym-filtered (may have multiple CID candidates)
3. **Tie-breaker:** Prefer lowest CID (typically parent compound, not mixture)
4. **Tracking:** All candidates stored in `cas_cid_candidates` table; `cid_ambiguous=1` flag set

**Validation:** Live PubChem picked different CID for 4 of 44 tested cases; bulk uses deterministic rule.

### LCSS Data Coverage

Extracted from `CID-LCSS.xml.gz` (257,169 records):

| Field | Source | Notes |
|-------|--------|-------|
| GHS H-codes | ✅ LCSS | Identical to live for 44/44 tested |
| GHS P-codes | ✅ LCSS | |
| GHS signal word | ✅ LCSS | |
| GHS pictograms | ✅ LCSS | |
| NFPA Health/Fire/Reactivity | ✅ LCSS | Identical to live for 44/44 tested |
| Flash point | ✅ LCSS | Converted to °C |
| Vapor pressure | ✅ LCSS | In mmHg |
| IARC classification | ✅ LCSS | |
| **LD50 (Toxicity Data)** | ❌ NOT IN LCSS | Differs ~1 in 6 vs live |
| **LC50/Aquatic (Ecotoxicity)** | ❌ NOT IN LCSS | Mostly lost |

### Source Flags

Results include explicit flags — **never silently blank**:

| Flag | Values | Meaning |
|------|--------|---------|
| `pubchem_source` | `"api"`, `"ftp_lcss"`, `"ftp_bulk"` | Where data came from |
| `toxicity_sections` | `"present"`, `"absent"` | Whether LD50/LC50 sections available |

### Offline Mode

When `PUBCHEM_OFFLINE_MODE=1`:
- All lookups use only local bulk index (no network calls)
- API calls raise `PubChemOfflineError` instead of attempting requests
- Does NOT write synthetic entries to HTTP cache
- Suitable for air-gapped or rate-limited environments

### CLI Commands

```bash
# Core files only (~1.1 GB download)
python -m packages.doss_core.pubchem_bulk build

# Include optional large files (~11 GB download)
python -m packages.doss_core.pubchem_bulk build --full

# Restrict index to specific CAS list
python -m packages.doss_core.pubchem_bulk build --cas-file expert_cas.txt

# Check and update if stale (>30 days)
python -m packages.doss_core.pubchem_bulk refresh

# Show index statistics
python -m packages.doss_core.pubchem_bulk status

# Look up a CAS number
python -m packages.doss_core.pubchem_bulk lookup 67-64-1

# Remove all bulk data
python -m packages.doss_core.pubchem_bulk clear --yes
```

### Environment Variables

| Variable | Purpose |
|----------|---------|
| `PUBCHEM_BULK_DIR` | Override bulk data directory (default `~/.turi-safe-chem-db/pubchem-bulk/`) |
| `PUBCHEM_DISABLE_BULK` | Set to `1` to skip bulk lookup entirely |
| `PUBCHEM_OFFLINE_MODE` | Set to `1` to block ALL live PubChem calls |

### Tests

| Test Category | Count | Description |
|--------------|-------|-------------|
| Multi-CID resolution | 4 | Identifiers vs synonyms priority, lowest CID rule |
| CAS absent from PubChem | 2 | Returns None / raises PubChemOfflineError |
| LCSS parsing | 6 | GHS, NFPA, flash point, vapor pressure |
| Streaming parser | 2 | Memory-bounded, generator-based |
| Offline mode | 3 | Blocks downloads, uses bulk, raises on miss |
| Integration | 2 | Bulk-first lookup, API fallback |

All tests use synthetic fixture files — **no live network calls**.

---

## PubChem PUG-REST API

**Status:** ✅ Implemented (throttle-hardened)
**Test coverage:** 32 unit tests

### Throttling Compliance

Implements [NCBI Dynamic Request Throttling](https://pubchem.ncbi.nlm.nih.gov/docs/dynamic-request-throttling):

| Behavior | Default | Env Override |
|----------|---------|--------------|
| Minimum request interval | 0.35s | `PUBCHEM_MIN_INTERVAL_S` |
| Max retries on 429/503 | 5 | `PUBCHEM_MAX_RETRIES` |
| Exponential backoff | Base 1.5s, max 60s, jitter | — |
| Honor Retry-After | Yes | — |
| Disk cache | 24h TTL | `PUBCHEM_CACHE_DIR`, `PUBCHEM_CACHE_MAX_AGE_S` |

### Fallback Behavior

1. Check local bulk index first (if available)
2. Check HTTP disk cache
3. Call PUG-REST API with throttling
4. On throttle failure: raise `PubChemThrottledError`
5. On offline mode: raise `PubChemOfflineError`

---

## Fisher SDS

**Status:** ✅ Implemented
**Notes:** Requires seed catalog (`data/fisher_catalog_by_cas.csv`)

---

## TCI SDS

**Status:** ✅ Implemented
**Notes:** Best-effort; may hit Akamai/403 blocks

---

## HSPiP Integration

**Status:** ✅ Implemented (due diligence)
**Notes:** Requires licensed `HSPiP.exe` and `.sofx` files (not shipped)
