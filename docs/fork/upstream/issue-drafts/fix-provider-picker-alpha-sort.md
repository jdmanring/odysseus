# Upstream Issue Draft: fix-provider-picker-alpha-sort

**File on:** `pewdiepie-archdaemon/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/fix-provider-picker-alpha-sort.md`
**Branch:** `fix/provider-picker-alpha-sort`
**Type:** Bug (UX)

## Title
`fix(providers): sort the Add API Models provider picker alphabetically`

## Body
The "Add API Models" provider picker renders providers in the raw static `<option>`
order. As providers were appended over time, that order drifted out of A–Z, so the
list is no longer alphabetical and providers are hard to find.

**Fix:** sort by label in `_renderPickerMenu` at render time (with the Custom URL
option pinned first), so the list stays alphabetical regardless of the underlying
append order. Case-insensitive `localeCompare`. Affected: `static/js/admin.js`.
