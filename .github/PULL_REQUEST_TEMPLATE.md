## Summary

<!-- Brief description of changes -->

## Type of Change

- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to change)
- [ ] Documentation update
- [ ] Refactoring (no functional changes)

## Related Issues

<!-- Link to related issues, e.g., Closes #123 -->

## Checklist

### General
- [ ] My code follows the project's style guidelines
- [ ] I have performed a self-review of my code
- [ ] I have added tests that prove my fix is effective or my feature works
- [ ] New and existing tests pass locally with my changes

### Capability Registry
- [ ] **Capability registry updated** — OR — **No capability added/removed**
- [ ] **No capability removed without note in CHANGELOG**
- [ ] If adding a capability: entry added to `capabilities.yaml` with all fields
- [ ] If adding a capability: test added to `tests/test_capabilities.py`
- [ ] If this PR is assigned TODO entries in `capabilities.yaml`: entries filled in

### Data & Configuration
- [ ] No hard-coded personal paths (use env vars or capability_config.py)
- [ ] Any new env vars documented in `CAPABILITIES.md`
- [ ] No silent skips — disabled features log why they are disabled

### Documentation
- [ ] README.md updated (if applicable)
- [ ] STATUS.md updated (if applicable)
- [ ] CAPABILITIES.md updated (if capabilities changed)

## Capability Report

<!-- Run `python -m packages.capability_report` and paste relevant output -->

```
# Paste capability report here if capabilities changed
```

## Test Results

<!-- Run `pytest tests/ -v` and confirm pass/skip status -->

```
# Paste test summary here
```

## Additional Notes

<!-- Any additional context or screenshots -->
