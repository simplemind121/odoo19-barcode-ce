## What this changes

<!-- One or two sentences. Link the issue: Fixes #123 -->

## Why

## How it was tested

<!-- Test names added or changed, and manual checks on real devices if any. -->

## Checklist

- [ ] `./scripts/test.sh` passes locally
- [ ] New behaviour has a Python test
- [ ] No Odoo Enterprise code was copied or adapted
- [ ] Scanner entry points start with `bc_guard()` and validate ids received from the client
- [ ] No stored field of a shared row is written on the scan hot path
- [ ] `CHANGELOG.md` updated under **Unreleased**
- [ ] `docs/compatibility.md` updated if behaviour relative to stock Odoo changed
- [ ] `docs/scanner-api.md` updated if a `bc_*` method or the state object changed
- [ ] Translations (`.pot`, `zh_CN.po`) updated if strings changed
- [ ] Manifest version bumped and migration added if the data model changed
