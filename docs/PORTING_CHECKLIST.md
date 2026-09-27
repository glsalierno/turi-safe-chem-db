# PORTING CHECKLIST — TURI Safe Chem DB

Guidelines for version updates, releases, and preventing capability loss.

## Golden Rule

> **New versions are branches, not folder copies.**

Never create a new version by copying folders. Use git branches for all versioning. This ensures:
- Full history and diff capability
- Proper merge conflict handling
- No accidental omission of files
- Traceability of every change

## Pre-Release Checklist

Before any release or version bump:

### 1. Run Capability Report

```bash
python -m packages.capability_report
```

Verify:
- [ ] All expected capabilities show `ACTIVE` or `OPTIONAL_SKIP`
- [ ] No unexpected `MISSING_DATA` or `DISABLED` status
- [ ] Any `TODO` entries are documented and expected

### 2. Run All Tests

```bash
pytest tests/ -v
```

Verify:
- [ ] All tests pass (or skip with explicit reason)
- [ ] No new test failures
- [ ] `test_capabilities.py` covers all registry entries

### 3. Check Capability Registry

Review `capabilities.yaml`:
- [ ] All capabilities have `status`, `module`, `test_id`, `env_vars`
- [ ] No TODO entries for features that are complete
- [ ] PR references are accurate

### 4. Verify Data Files

Ensure bundled data is present:
- [ ] `data/p2oasys_score_lookup.sqlite` — P2OASys scores
- [ ] `data/fisher_catalog_by_cas.csv` — Fisher catalog
- [ ] `data/priority_expert_p2oasys_scores.csv` — Optional expert overlay

### 5. Update Documentation

- [ ] README.md reflects current features
- [ ] STATUS.md is current
- [ ] CAPABILITIES.md matches capabilities.yaml
- [ ] CHANGELOG includes all notable changes

## Dropping a Capability

**Never silently drop a capability.** If a feature must be removed:

1. **Document in CHANGELOG** with:
   - Capability name
   - Reason for removal
   - Migration path (if any)
   - PR/commit reference

2. **Update capabilities.yaml**:
   - Change status to `deprecated` or remove entirely
   - Add note in comments about removal date

3. **Remove or archive code**:
   - Delete the module, or
   - Move to `archive/` with deprecation notice

4. **Update tests**:
   - Remove or skip the capability test
   - Add comment explaining removal

5. **Notify users**:
   - Add migration note to README
   - Consider keeping stub that logs deprecation warning

Example CHANGELOG entry:
```markdown
### Removed
- **XYZ capability** — Removed due to API deprecation. Use ABC instead.
  See PR #123 for migration guide.
```

## Version Numbering

Follow semantic versioning:
- **MAJOR**: Breaking changes (capability removal, API changes)
- **MINOR**: New capabilities, backward-compatible features
- **PATCH**: Bug fixes, documentation

## Teams Pack Sync

When updating the Teams pack (`TURI-SafeChemDB-TeamsPack`):

1. Sync from git repo to Teams pack `app/` folder:
   ```bash
   robocopy turi-safe-chem-db TURI-SafeChemDB-TeamsPack\app /MIR ^
     /XD .git .venv __pycache__ .pytest_cache ^
     /XF *.pyc
   ```

2. Verify capability report runs in Teams pack environment

3. Test with coworker machine (no developer tools)

## CI/CD Integration

The capability report should run in CI:

```yaml
# Example GitHub Actions
- name: Capability Report
  run: python -m packages.capability_report

- name: Run Tests
  run: pytest tests/ -v --tb=short
```

Fail the build if:
- Required capabilities show `MISSING_DATA`
- Any test fails (not just skips)
- Registry integrity tests fail

## Troubleshooting

### "Module not found" for active capability

1. Check `PYTHONPATH` includes repo root
2. Verify module path in capabilities.yaml is correct
3. Check for import errors in the module itself

### "MISSING_DATA" for expected capability

1. Check env var is set correctly
2. Verify data file exists at expected path
3. Check file permissions

### Test skips with "TODO"

Normal for planned features. Verify:
1. Capability status is `TODO` in registry
2. PR reference is accurate
3. Test explicitly states the reason

## Quick Reference

```bash
# Run capability report
python -m packages.capability_report

# Run capability report (verbose)
python -m packages.capability_report -v

# Run capability report (JSON output)
python -m packages.capability_report --json

# Run all tests
pytest tests/ -v

# Run capability tests only
pytest tests/test_capabilities.py -v

# Check registry integrity
pytest tests/test_capabilities.py -k "test_every" -v
```
