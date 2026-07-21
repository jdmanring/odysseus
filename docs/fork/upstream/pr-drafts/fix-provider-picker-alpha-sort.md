# PR Draft: fix/provider-picker-alpha-sort → odysseus-dev/odysseus:dev

**Branch:** `fix/provider-picker-alpha-sort`
**Fork issue:** [#122](https://github.com/jdmanring/odysseus/issues/122)
**Status:** Single clean commit. File the upstream issue first, fill `Fixes #___`, then open the PR.

## Upstream PR title
`fix(providers): sort the Add API Models provider picker alphabetically`

## Summary

### Problem
The "Add API Models" provider picker renders providers in the raw static `<option>`
order. As providers were appended over time that order drifted out of A–Z, so the
list is no longer alphabetical and a provider is hard to locate.

### Fix
Sort by label in `_renderPickerMenu` at render time, with the Custom URL option
pinned first (`filter(o => !o.value)`), using case-insensitive `localeCompare`. The
list now stays alphabetical regardless of the underlying append order; no data model
change.

## How to Test
1. Open Settings → Add API Models → open the provider picker.
   - **Expected:** providers are listed A–Z, with Custom URL first.
   - **Before this fix:** providers appear in append order (not alphabetical).
2. Selecting a provider still populates its endpoint as before.

### Tests
`tests/test_provider_picker_sort_js.py` — a source-audit guard asserting
`_renderPickerMenu` sorts via case-insensitive `localeCompare`. (A DOM/behaviour
test would be stronger; this locks the sort call and pin-first ordering.)

## Scope
One file (`static/js/admin.js`), render-time sort only. No change to the provider
data or selection behavior.

## Target branch
`dev` (never `main`).

## Fixes
`Fixes #___` (fill with the upstream issue number after filing).
