# CAPABILITIES — TURI Safe Chem DB

This document lists all capabilities (features) in the TURI Safe Chem DB project.
See `capabilities.yaml` for the machine-readable registry with module paths, env vars, and test IDs.

## Purpose

The capability registry ensures:
1. **No silent feature loss** — Every capability has a test and is tracked
2. **Clear configuration** — All env vars and data paths documented in one place
3. **Version parity** — Running `python -m packages.capability_report` shows what's enabled
4. **PR accountability** — TODO entries must be filled before PRs merge

## Status Legend

| Status | Meaning |
|--------|---------|
| ✅ **active** | Implemented and tested |
| 🔶 **optional** | Works when external data/license is configured; skip otherwise |
| 📝 **TODO** | Planned; PR must fill this entry before merge |
| ⬜ **stub** | Module exists but not yet functional |
| 🔒 **licensed** | Requires proprietary software/data |

---

## PubChem API

| Capability | Status | Description |
|------------|--------|-------------|
| **PubChem PUG-REST** | ✅ active | CAS→CID lookup, identity, physchem via REST API |
| **PubChem PUG-View GHS** | ✅ active | Extended hazard data (GHS codes, NFPA ratings) |
| **PubChem FTP bulk** | 📝 TODO (#7) | Bulk compound index for offline lookups |

### Environment Variables
- `PUBCHEM_MIN_INTERVAL_S` — Minimum seconds between requests (default 0.35)
- `PUBCHEM_MAX_RETRIES` — Max retries on 429/503 (default 5)
- `PUBCHEM_CACHE_DIR` — Custom cache directory (default `data/cache/pubchem/`)
- `PUBCHEM_CACHE_MAX_AGE_S` — Cache TTL in seconds (default 86400)
- `PUBCHEM_BULK_DIR` — Directory for bulk FTP index (PR #7)
- `PUBCHEM_DISABLE_BULK` — Set `1` to disable bulk lookups (PR #7)

---

## P2OASys Scoring

| Capability | Status | Description |
|------------|--------|-------------|
| **P2OASys score lookup** | ✅ active | Expert/auto overall scores from bundled SQLite |
| **P2OASys matrix + scorer** | ✅ active | Full hazard matrix computation (v6.7 from PR #8/#10) |

### Environment Variables
- `P2OASYS_SCORE_LOOKUP_DB` — Override path to score lookup SQLite
- `EXPERT_P2OASYS_CSV` — Optional expert CSV overlay
- `P2OASYS_DATA_DIR` — Directory for hazard matrix and reference data

---

## Auto P2OASys (PR F)

Clean automatic P2OASys scoring with expert-first routing and fast pipeline fallback.

| Capability | Status | Description |
|------------|--------|-------------|
| **auto_p2oasys()** | ✅ active | Main entry point with expert-first routing |
| **Expert lookup** | ✅ active | Returns expert scores when available (mode=`expert`) |
| **Fast pipeline** | ✅ active | Runs adapters when expert missing or `force_fast=True` |
| **Expert+fast mode** | ✅ active | Returns both when `force_fast=True` (mode=`expert+fast`) |
| **Evidence records** | ✅ active | Traceable evidence from each source |
| **Source report** | ✅ active | Shows which adapters ran/skipped/disabled |
| **CLI** | ✅ active | `python -m packages.auto_p2oasys --cas ... [--fast]` |

### Adapters

| Adapter | Status | Description |
|---------|--------|-------------|
| **PubChem identity** | ✅ active | CID, SMILES, MW from PubChem |
| **PubChem hazard** | ✅ active | GHS, NFPA, flash point, VP from PubChem |
| **CAMEO NFPA** | ✅ active | NFPA 704 from bundled CAMEO sqlite |
| **IARC table** | ✅ active | IARC carcinogen classification |
| **EPA carcinogen** | ✅ active | EPA IRIS carcinogen classification |
| **ODP/GWP tables** | ✅ active | ODP and GWP100 from bundled tables |
| **CAA HAP list** | ✅ active | Clean Air Act §112(b) HAP list |
| **Odor threshold** | ✅ active | Odor threshold lookup (flags MISSING if unavailable) |
| **SDS offline parse** | ✅ active | Structured SDS PDF parse (upload or cache) with 20+ fields |
| **OPERA predictions** | 🔶 optional | Log Kow, BCF, biodeg from OPERA cache |
| **ECOSAR predictions** | 🔶 optional | Aquatic LC50 via pyepisuite API |
| **HSPiP VP** | 🔒 licensed | Vapor pressure from HSPiP (optional) |
| **Flash point predict** | 🔶 wired_local | Maestri FPT model (measured first, then fallback) - see below |
| **IUCLID endpoints** | 🔶 optional | ECHA REACH study results (see attribution below) |
| **ToxValDB** | 🔶 optional | CompTox ToxValDB (API key required) |
| **CPDB** | 🔶 optional | Carcinogenic Potency DB (sqlite not bundled) |
| **DSSTox** | 🔶 optional | CompTox chemical identifiers (DTXSID, SMILES) |
| **IPCC GWP** | 🔶 optional | IPCC AR4-AR6 Global Warming Potential lookup |
| **Atmospheric rules** | ✅ active | Acid rain precursor, default GWP/ODP values |
| **pH cascade** | ✅ active | pH estimation (experimental, pKa, SMARTS heuristic) |

### IUCLID Endpoints (with ECHA Attribution)

When IUCLID cache is available, these endpoints are wired:
- Inhalation LC50
- Repeated dose toxicity
- Genotoxicity (in vitro and in vivo)
- Biodegradation
- Chronic aquatic NOEC

**CRITICAL ATTRIBUTION REQUIREMENT:**
Any result derived from IUCLID data **must** display:
```
Source: ECHA REACH Study Results (IUCLID), European Chemicals Agency
```
This attribution is automatically added to all IUCLID-sourced evidence.

### NOT_WIRED Endpoints

These endpoints are explicitly marked as not yet implemented:
- **IDLH** (Immediately Dangerous to Life or Health)
- **Reportable Quantity** (CERCLA/EPCRA)

### Gap-Fill Layer

For each of the 34 auto subcategories (Acute 9, Chronic 7, Ecological 2, Fate 3, Atmospheric 4, Physical 9):
- Try pathways in order, measured before predicted
- Stop at first reliable one (P2OASys OR-of-pathways)
- Keep other evidence in trace
- Predicted-only values labeled

### ECOSAR Gap-Fill Rule

**Rule (Gabriel decision 2026-09-28):** ECOSAR may fill Ecological subcategories ONLY when
no measured data exists for that subcategory.

**Measured data definition:**
- Measured LC50/EC50/NOEC values (marked `predicted=false`)
- GHS aquatic H-phrases (H400, H410, H411, H412, H413)

The GHS aquatic H-phrases are assigned based on measured aquatic toxicity data:
| H-Code | Meaning | Basis |
|--------|---------|-------|
| H400 | Very toxic to aquatic life | LC50 ≤ 1 mg/L |
| H410 | Very toxic with long lasting effects | LC50 ≤ 1 AND NOEC ≤ 0.1 |
| H411 | Toxic with long lasting effects | 1 < LC50 ≤ 10 AND NOEC ≤ 1 |
| H412 | Harmful with long lasting effects | 10 < LC50 ≤ 100 |
| H413 | May cause long lasting harmful effects | Rapid degradation, NOEC > 1 |

**Requirements:**
1. Measured data ALWAYS wins over ECOSAR — never averaged together
2. Every ECOSAR-derived unit is labelled `predicted=true` and counted in `predicted_only_categories`
3. Fix 4 caps remain in effect:
   - Inorganics, polymers, siloxanes (ECOSAR not applicable)
   - Predictions far below water solubility (implausible "no effect at saturation")

**Tests:**
- `test_measured_wins_over_ecosar` — when measured LC50 exists, ECOSAR is not used
- `test_ecosar_fills_gap` — when no measured data, ECOSAR fills with predicted label

### Maestri Flash Point Model (wired_local_models)

XGBoost-based flash point prediction with applicability domain checking.

**Model Provenance:**
- Code: [Zenodo 10.5281/zenodo.20931012](https://doi.org/10.5281/zenodo.20931012) ("mlmaestri/VariablePrediction: pre_release", CC-BY-4.0)
- Training data: DIPPR flash point n=1248 (licensed, not redistributable)
- Model metrics: R² = 0.944, RMSE = 14.81 K, MAE = 8.01 K

**CRITICAL:** Trained models (`fpt_model_zenodo10.joblib` etc.) are trained on licensed
HSPiP/DIPPR/Yaws data and **MUST NOT** be committed to public repo.

**Gap-fill order for flash point:**
1. Measured (PubChem/SDS/CAMEO/IUCLID) — preferred
2. Maestri prediction — labeled "Predicted (Maestri FPT model)" with AD result

**Applicability Domain:**
- Features within training range
- Mean 5-NN distance ≤ 95th percentile of training distances
- Out-of-domain predictions are flagged and **must not drive overall on their own**

### Environment Variables
- `AUTO_P2OASYS_OFFLINE` — Set `1` to disable network adapters (use fixtures)
- `TURI_FPT_MODEL_DIR` — Directory containing Maestri FPT model files (local only)
- `ECOSAR_API_URL` — pyepisuite API endpoint for ECOSAR
- `OPERA_PRECOMPUTE_DB_PATH` — Path to OPERA precompute cache
- `CAMEO_NFPA_DB` — Path to CAMEO NFPA SQLite

### CLI Usage

```bash
# Expert score from lookup (offline)
python -m packages.auto_p2oasys --cas 67-64-1

# Force fast pipeline (expert+fast mode)
python -m packages.auto_p2oasys --cas 67-64-1 --fast

# Parse SDS PDF for CAS and data
python -m packages.auto_p2oasys --sds tfa.pdf

# JSON output
python -m packages.auto_p2oasys --cas 67-64-1 --json result.json
```

---

## SDS Enrichment

| Capability | Status | Description |
|------------|--------|-------------|
| **Fisher SDS enrich** | ✅ active | Fisher Scientific SDS/catalog (NFPA, pricing, physchem) |
| **TCI SDS enrich** | ✅ active | TCI SDS/catalog enrichment |
| **Sigma SDS enrich** | ⬜ stub | MilliporeSigma access pending |
| **SDS offline parse** | ✅ active | Structured offline parse from upload or cache |

### Environment Variables
- `DOSS_ENABLE_FISHER` — Default for Fisher toggle (`1`/`0`; default on)

---

## SDS Offline Parse (PR #12)

Full structured SDS parsing from sections 2/8/9/10/11/12/14 plus NFPA. **Offline only** - no network, no OCR, no LLM.

### CLI Options
```bash
# Explicit PDF upload (takes precedence over cache)
python -m packages.auto_p2oasys --cas 67-64-1 --sds myfile.pdf

# Use offline cache directory
python -m packages.auto_p2oasys --cas 67-64-1 --sds-cache /path/to/cache

# Include mixture/solution SDS values in scoring
python -m packages.auto_p2oasys --cas 67-64-1 --sds-cache /path/to/cache --sds-allow-mixture
```

### Environment Variables
- `TSCD_SDS_CACHE_DIR` — Offline SDS cache root directory
- `TSCD_SDS_ALLOW_MIXTURE` — Include mixture SDS values (`1`/`true`/`yes`; default off)

### Cache Layout
```
<DIR>/<cas>/<vendor>/<revision>/<sha256[:12]>/original.pdf
           optional: metadata.json (with "revision", "manufacturer", "stored_at")
```
CAS folders may use dashes (`67-64-1`) or digits-only (`67641`). Both are searched.

### Parsed Fields → P2OASys Subcategories

| Parsed Field | Endpoint | P2OASys Subcategory |
|--------------|----------|---------------------|
| Section 2 H-codes | `h_codes` | Oral/Dermal/Inhalation, Irritation, Carcinogen, Aquatic, etc. |
| NFPA Health/Fire/Instability | `nfpa_*` | Health, Flammability, Reactivity |
| Section 9 flash point (°C) | `flash_point` | Flammability: Liquid |
| Section 9 vapor pressure (mmHg) | `vapor_pressure` | Vapor Pressure |
| Section 9 pH | `ph` | pH |
| Section 9 odor | `sds_phrase` (normalized) | Odor |
| Section 11 oral/dermal LD50 | `oral_ld50`, `dermal_ld50` | Oral/Dermal Toxicity |
| Section 11 inhalation LC50 | `inhalation_lc50` | Inhalation Toxicity |
| Section 12 aquatic LC50/EC50 | `aquatic_lc50_*` | Acute Aquatic Toxicity |
| Section 12 NOEC | `chronic_aquatic_noec` | Chronic Aquatic Toxicity |
| Section 12 BCF | `bcf` | Bioaccumulation |
| Section 12 log Kow | `log_kow` | Bioconcentration |
| Section 12 phrase cues | `sds_phrase` | Rapid Degradability, Persistence |

### Unmapped Fields (logged but not scored)
- Exposure limits (PEL/TLV/REL/STEL) — scorer unit not mapped
- Persistence/biodegradation half-life text — scorer unit not mapped
- Boiling point — no scorer unit
- Section 10 incompatible materials text
- Section 14 UN number/class (except Class 8 → Corrosivity cue)

### Mixture/Solution Detection
A mixture flag is set when:
- ≥2 valid CAS numbers in section 3 with concentration ≥1%
- Target CAS concentration <90%
- Target CAS absent while other CAS present
- Product name matches pattern (e.g., "37% solution")

By default, mixture SDS values are held out of scoring. Use `--sds-allow-mixture` to include them with a reliability label.

### Source Labeling
All SDS evidence carries:
- `source = "SDS (Vendor, filename.pdf)"`
- `source_type = "SDS"`
- `section = "Section N"`
- `reliability = "measured"` or `"classification"`
- `predicted = False` (except for estimated/QSAR values in section 12)

---

## HSPiP Hansen Solubility Parameters

| Capability | Status | Description |
|------------|--------|-------------|
| **HSPiP sofx lookup** | 🔶 optional/🔒 | D/P/H/RER from local .sofx files |
| **HSPiP CLI** | 🔶 optional/🔒 | HSPiP.exe Y-MBSX for SMILES→D/P/H |
| **Glove HSP screen** | ✅ active | HSP-based glove polymer compatibility |

### Environment Variables
- `HSPIP_DATA` / `HSPIP_DATA_DIR` — Directory of .sofx libraries
- `HSPIP_EXE` / `HSPIP_PATH` — Path to HSPiP.exe or install folder

### Notes
- HSPiP software and .sofx files are **licensed** and never shipped with this repo
- Obtain HSPiP from [hansen-solubility.com](https://www.hansen-solubility.com/HSPiP)
- Close HSPiP GUI before using CLI (they contend for locks)

---

## Hazard Reference Tables (Scorer)

| Capability | Status | Description |
|------------|--------|-------------|
| **CAMEO NFPA sqlite** | 📝 TODO (#1) | CAMEO Chemicals NFPA 704 ratings |
| **IARC table** | 📝 TODO (#8) | IARC carcinogen classification |
| **ODP/GWP/IPCC atmo** | 📝 TODO (#8) | Ozone/GWP atmospheric tables |
| **CAA HAP list** | 📝 TODO (#8) | Clean Air Act HAP list |

### Environment Variables
- `CAMEO_NFPA_DB` — Path to CAMEO NFPA SQLite
- `IARC_TABLE_PATH` — Path to IARC CSV/table
- `ODP_GWP_TABLE_PATH` — Path to ODP/GWP tables
- `CAA_HAP_LIST_PATH` — Path to CAA HAP list

---

## GHaz7/GHaz8 Stack (from fast P2OASys)

| Capability | Status | Description |
|------------|--------|-------------|
| **CompTox / DSSTox lookup** | 📝 TODO (#8) | EPA CompTox Dashboard DSSTox lookup |
| **ToxVal / ToxValDB lookup** | 📝 TODO (#8) | EPA ToxValDB API for toxicity values |
| **OPERA predictions** | 📝 TODO (#8) | NIEHS OPERA 2.9 QSAR predictions (licensed) |
| **GHaz7 headless CLI** | ❓ MISSING | Headless auto-P2OASys CLI (needs re-rooting) |
| **fast P2OASys v2 batch** | 📝 TODO (#8) | High-throughput batch scoring |

### Environment Variables
- `DSSTOX_CACHE_PATH` — DSSTox parquet cache path
- `COMPTOX_API_KEY` — CompTox Dashboard API key
- `EPA_API_KEY` — EPA API key for ToxValDB
- `OPERA_EXE_PATH` — Path to OPERA 2.9 executable
- `OPERA_CACHE_DB` — OPERA results cache SQLite
- `P2OASYS_HARVEST_DB` — P2OASys harvest results database

### Notes
- OPERA requires the NIEHS OPERA 2.9 MATLAB-compiled executable (licensed)
- GHaz7 headless CLI exists but needs layout adaptation for turi-safe-chem-db

---

## External Tools

| Capability | Status | Description |
|------------|--------|-------------|
| **ECOSAR/pyepisuite** | 📝 TODO (#6) | Aquatic toxicity and EPI Suite estimation |
| **IUCLID dossiers** | 📝 TODO (#9) | IUCLID 6 dossier access |

### Environment Variables
- `EPISUITE_PATH` — Path to EPI Suite installation (PR #6)
- `ECOSAR_DISABLE` — Set `1` to disable ECOSAR (PR #6)
- `IUCLID_API_URL` — IUCLID API endpoint (PR #9)
- `IUCLID_API_KEY` — IUCLID API key (PR #9)

---

## Scorer Fixes (PR #10)

| Capability | Status | Description |
|------------|--------|-------------|
| **Beyond-solubility checks** | 📝 TODO (#10) | Handle values beyond solubility limits |
| **Suspicious input checks** | 📝 TODO (#10) | Validation for malformed inputs |
| **Unit conversion hardening** | 📝 TODO (#10) | Robust mg/m³→ppm conversion |

---

## Core Application

| Capability | Status | Description |
|------------|--------|-------------|
| **DoSS app** | ✅ active | Streamlit DoSS row generator |
| **assess() spine** | ⏹️ superseded | Core assessment — superseded by auto_p2oasys (PR F) |

### Environment Variables
- `PYTHONPATH` — Set to repo root if not using editable install

---

## Quick Reference: All Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `PUBCHEM_MIN_INTERVAL_S` | Min request interval | 0.35 |
| `PUBCHEM_MAX_RETRIES` | Max retries on throttle | 5 |
| `PUBCHEM_CACHE_DIR` | PubChem cache location | `data/cache/pubchem/` |
| `PUBCHEM_CACHE_MAX_AGE_S` | Cache TTL | 86400 |
| `P2OASYS_SCORE_LOOKUP_DB` | P2OASys score SQLite | `data/p2oasys_score_lookup.sqlite` |
| `EXPERT_P2OASYS_CSV` | Expert CSV overlay | (none) |
| `DOSS_ENABLE_FISHER` | Fisher toggle default | 1 |
| `HSPIP_DATA` | HSPiP .sofx directory | (none) |
| `HSPIP_EXE` | HSPiP.exe path | (none) |

---

## Running the Capability Report

```bash
# Show status of all capabilities
python -m packages.capability_report

# Output shows ACTIVE, DISABLED, or MISSING_DATA for each capability
```

The report runs at startup of apps and batch CLIs to surface any missing configuration.

---

## For Contributors

1. **Adding a capability**: Add entry to `capabilities.yaml` with all fields; add test to `tests/test_capabilities.py`
2. **Removing a capability**: Document removal in CHANGELOG with reason; never silently drop
3. **PR checklist**: All TODO entries assigned to your PR must be filled before merge

See [docs/PORTING_CHECKLIST.md](docs/PORTING_CHECKLIST.md) for version/release guidance.
