# Idle-Reclaim Threshold — Research & Citable Basis

**Component:** `qt_wrapper.py` renderer reclaim (`_IDLE_RECLAIM_AFTER_S`, env `ODYSSEUS_IDLE_RECLAIM_S`)
**Decision:** default **60 seconds**, per the W3C/WICG Idle Detection API standard (not a guess).
**Date:** 2026-06-25 · Related: #106 (renderer reclaim)

---

## Problem

The renderer reclaim fires a forcible purge (`Memory.forciblyPurgeJavaScriptMemory`) when the
user is "idle". That purge **blocks the renderer ~1 s** (a synchronous, full GC + cache drop).
The original threshold was **3 s** of no input — far too short: a 3-second reading/thinking
pause is *active use*, not "away". Consequences observed:

- A ~1 s **stutter** every time it fired mid-session.
- When the freeze dropped a mid-drag `mouseup`, **Chromium's left-button input state got stuck**
  — left-click stopped working while right-click (a different button) still did.

## Why we can't just make the purge non-blocking ("lazy")

There is **no lazy/async purge on QtWebEngine**:

- The CDP `Memory` domain's *only* reclamation method is `forciblyPurgeJavaScriptMemory`,
  described as *"Simulate OomIntervention by purging V8 memory"* — synchronous, no incremental
  variant. ([CDP Memory domain](https://chromedevtools.github.io/devtools-protocol/tot/Memory/))
- The mechanism that *would* be lazy — Chromium's `MemoryPressureListener` incremental cache
  eviction, triggered by `simulatePressureNotification` — is a **no-op on Linux** (Chromium's
  memory-pressure signals do not function on Linux), and QtWebEngine does not forward OS pressure
  to the renderer. ([Chromium OOM/pressure design](https://www.chromium.org/chromium-os/chromiumos-design-docs/out-of-memory-handling/),
  [memory-pressure on Linux, crbug 813909](https://bugs.chromium.org/p/chromium/issues/detail?id=813909))
- V8 async GC (`gc({execution:'async'})`) is non-blocking but reclaims only the JS heap (a small
  fraction); the bulk freed by the purge is renderer caches (raster/transfer/decoded-image/Blink).

So the heavy reclaim is unavoidably blocking. The fix is therefore **when**, not **how**: only
fire it when the user is genuinely away, so the unavoidable ~1 s freeze never lands on input.

## The standard (the citable source)

"Genuinely away / idle" has an **established web standard**, not a number to guess: the
**W3C / WICG Idle Detection API**. It defines `userState` ∈ {active, idle} and **restricts the
idle `threshold` to a minimum of 60 seconds (60,000 ms)**.

> *"This specification therefore restricts the requested threshold to a minimum of at least
> 60 seconds."* — WICG Idle Detection API spec.

Rationale (from the spec/MDN): below ~60 s you are not detecting *idle*, you are detecting a
*pause* — and a short threshold is a security side-channel (it can leak typing cadence /
presence in another app). Practitioner guidance: **30–120 s** depending on use case (chat/
presence at the low end; billing / long-form editors longer).

**Sources (citable):**
- MDN — Idle Detection API: <https://developer.mozilla.org/en-US/docs/Web/API/Idle_Detection_API>
- WICG spec (the 60 s floor): <https://wicg.github.io/idle-detection/>
- Chrome for Developers — Detect inactive users: <https://developer.chrome.com/docs/capabilities/web-apis/idle-detection>

## Decision

- **Default `_IDLE_RECLAIM_AFTER_S` = 60 s** — the standard's minimum, and the principled safe
  choice for a *disruptive* (blocking) reclaim.
- **Tunable** via `ODYSSEUS_IDLE_RECLAIM_S` for users who deliberately want more aggressive
  reclaim (lower) and accept the stutter risk; floored at 2 s. Going below 60 s means reclaiming
  on pauses, not idle — by the standard's own definition.
- The **switched-away / minimized** cases reclaim *immediately* (no 60 s wait) via the separate
  focus-loss and minimize purges — the equivalent of acting on the Page Visibility / window-blur
  signal, which is the standard's complement for "user left."

Guarded by `tests/test_idle_purge_threshold.py` (default must meet the ≥60 s standard).
