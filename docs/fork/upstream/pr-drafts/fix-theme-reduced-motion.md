# PR Draft: fix/theme-reduced-motion -> odysseus-dev/odysseus:dev

**Branch:** `fix/theme-reduced-motion`
**Status:** Ready to file
**Base:** cut from `upstream-mirror`, 2 files, +43/-1

---

## Title

`fix(theme): honor prefers-reduced-motion for canvas background effects`

---

## Summary

### Problem

Seven canvas background effects - synapse, rain, constellations, perlin-flow,
petals, sparkles, embers - repaint under the whole UI **every animation frame**
and ignore the OS reduce-motion request entirely.

This is an accessibility defect first: a user who has asked the system to reduce
motion gets full-screen continuous animation anyway, and the setting exists
because that motion causes real symptoms for some people.

It is also the **largest per-frame CPU cost on software-rendered machines**.
Verified on the macOS Tahoe bench, where no GPU acceleration exists for guests:
with system Reduce Motion on, canvas count drops to 0 and full-page repaint churn
stops.

### Fix

Gate the effect launch on `prefers-reduced-motion` at the single `applyBgPattern`
choke point. The theme's **static pattern is kept**, so the visual identity
survives; only the animation stops.

One choke point matters here: the login page routes through the same function, so
gating there covers it without a second code path to keep in sync.

The media query is **live** - toggling the OS setting re-applies without a
reload, which is the behaviour a user testing the setting expects.

---

## Verification

**3 passed**, measured 2026-08-03: a static guard that the gate exists at the
choke point and that the static pattern is retained.

Behaviourally confirmed on the Tahoe bench as above (canvas count 0 with the
setting on).

---

## Scope

`static/js/theme.js` (+16/-1) and one test file. No change for users who have not
requested reduced motion.
