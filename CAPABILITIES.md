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
| **P2OASys matrix + scorer** | 📝 TODO (#8) | Full hazard matrix computation |

### Environment Variables
- `P2OASYS_SCORE_LOOKUP_DB` — Override path to score lookup SQLite
- `EXPERT_P2OASYS_CSV` — Optional expert CSV overlay
- `P2OASYS_MATRIX_DIR` — Directory for hazard matrix data (PR #8)

---

## SDS Enrichment

| Capability | Status | Description |
|------------|--------|-------------|
| **Fisher SDS enrich** | ✅ active | Fisher Scientific SDS/catalog (NFPA, pricing, physchem) |
| **TCI SDS enrich** | ✅ active | TCI SDS/catalog enrichment |
| **Sigma SDS enrich** | ⬜ stub | MilliporeSigma access pending |

### Environment Variables
- `DOSS_ENABLE_FISHER` — Default for Fisher toggle (`1`/`0`; default on)

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
| **CAMEO NFPA sqlite** | 📝 TODO (#8) | CAMEO Chemicals NFPA 704 ratings |
| **IARC table** | 📝 TODO (#8) | IARC carcinogen classification |
| **ODP/GWP/IPCC atmo** | 📝 TODO (#8) | Ozone/GWP atmospheric tables |
| **CAA HAP list** | 📝 TODO (#8) | Clean Air Act HAP list |

### Environment Variables
- `CAMEO_NFPA_DB` — Path to CAMEO NFPA SQLite
- `IARC_TABLE_PATH` — Path to IARC CSV/table
- `ODP_GWP_TABLE_PATH` — Path to ODP/GWP tables
- `CAA_HAP_LIST_PATH` — Path to CAA HAP list

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

## Core Application

| Capability | Status | Description |
|------------|--------|-------------|
| **DoSS app** | ✅ active | Streamlit DoSS row generator |
| **assess() spine** | 📝 TODO (#5) | Core assessment orchestration |

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
