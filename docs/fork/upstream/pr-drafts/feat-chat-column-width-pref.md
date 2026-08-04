# PR Draft: feat/chat-column-width-pref -> odysseus-dev/odysseus:dev

**Branch:** `feat/chat-column-width-pref`
**Status:** Ready to file
**Base:** cut from `upstream-mirror`, 4 files, +101/-1

---

## Title

`feat(settings): chat column width preference`

---

## Summary

### Problem

The chat renders in a monospace font by default, so the hard-coded
`--chat-max: 800px` column is effectively a **characters-per-line setting stuck
at 63**.

That is narrow by typographic convention. Line-length guidance for readability
generally lands in the 66-80 character range, and 63 sits below it — while the
user's window is usually much wider, so the constraint is not coming from the
display.

### Fix

A **Chat width** select in the theme panel: 800 / 900 / 1000 / 1200px, labelled
with the character counts they produce (verified by live measurement, not
computed from an assumed advance width). 1000px is a standard 80-column reading
width.

Persisted in `localStorage` and applied live as a `--chat-max-user` CSS variable
that `.chat-history`'s `--chat-max` falls back from.

Applied in the head boot script as well, for the same no-flash reason as the
existing ui-scale preference — **whose pattern this mirrors exactly**, so it adds
a preference without adding a mechanism.

### Default unchanged

Still 800px. The override is *removed* rather than pinned when the user selects
the default, so CSS remains the single source of the default value and a future
change to it is not silently overridden by stale `localStorage`.

---

## Verification

**6 passed**, measured 2026-08-03: the variable fallback chain, persistence, the
head-boot application, and that selecting the default clears rather than pins.

---

## Scope

`static/js/theme.js` (+29), `static/index.html` (+13), one CSS line, one test
file.
