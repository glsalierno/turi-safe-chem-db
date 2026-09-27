# IUCLID Test Fixtures

These are **SYNTHETIC** test fixtures that mirror the structure of IUCLID 6 dossiers
but contain fabricated data for testing purposes only.

**IMPORTANT:** These fixtures do NOT contain any actual ECHA REACH Study Results data.
All values, UUIDs, and structure are created purely for automated testing.

## Files

- `synthetic_phrases.json` - Minimal phrase code → label map for tests
- `synthetic_dossier/` - Synthetic .i6z dossier structure (created at test time)
- `synthetic_index.csv` - Fake CAS → UUID mapping for tests

## Structure Reference

A real IUCLID 6 `.i6z` dossier is a ZIP containing:
- `manifest.xml` - Dossier metadata
- `<uuid>.i6d` files - Individual documents (substances, endpoints, etc.)

Each ENDPOINT_STUDY_RECORD.* document contains:
- `AdministrativeData/Reliability` - Klimisch score phrase code
- `AdministrativeData/PurposeFlag` - key study / supporting study
- `AdministrativeData/StudyResultType` - experimental / (Q)SAR
- `MaterialsAndMethods/TestAnimals/Species` - Species phrase code
- `MaterialsAndMethods/AdministrationExposure/RouteOfAdministration` - Route
- `ResultsAndDiscussion/EffectLevels/entry` - Acute tox results
- `ResultsAndDiscussion/EffectConcentrations/entry` - Aquatic tox results
- etc.

See IUCLID 6 documentation for full schema details.
