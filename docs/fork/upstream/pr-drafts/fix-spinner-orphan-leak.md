# PR Draft: fix/spinner-orphan-leak -> odysseus-dev/odysseus:dev

**Branch:** `fix/spinner-orphan-leak`
**Status:** Ready to file
**Base:** cut from `upstream-mirror`, 2 files, +99/-8

---

## Title

`fix(spinner): stop orphaned and hidden spinner animation loops`

---

## Summary

### Problem

All three animated spinners run a continuous loop — whirlpool and sinewave via
`requestAnimationFrame`, ASCII via `setInterval`. Nothing stops them if the
element never reaches the document, or if the panel holding it closes.

An orphaned spinner loops **forever**. In a normal browser tab that is wasted
CPU; in an embedded Chromium wrapper the raster work is never reclaimed and
accumulates across a session.

### Fix

One shared `_shouldKeepSpinning()` guard used by all three loops: keep going only
while the element actually renders a box, with a bounded grace window for the
legitimate not-yet-appended case (a spinner is often `start()`ed before being
inserted).

**The predicate choice is the substance of this change.** Three candidates, and
two of them are wrong in ways that only show up in specific layouts:

| check | why it fails |
|---|---|
| `offsetParent` | `null` for a **visible** element inside a `position: fixed` overlay — would kill spinners in every modal |
| `isConnected` | stays `true` for `display: none` — would not stop a hidden spinner at all |
| **`getClientRects().length`** | true only for rendered elements, and correct under `position: fixed` |

`getClientRects().length` is the one that answers the actual question: does this
element render a box right now.

---

## Verification

**5 passed**, measured 2026-08-03.

---

## Scope

`static/js/spinner.js` (+49/-8) and one test file. No API change: callers keep
calling `start()`/`stop()` as before.
