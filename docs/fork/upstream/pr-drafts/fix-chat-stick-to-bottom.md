# PR Draft: fix/chat-stick-to-bottom -> odysseus-dev/odysseus:dev

**Branch:** `fix/chat-stick-to-bottom`
**Status:** Ready to file
**Base:** cut from `upstream-mirror`, 4 files, +255/-6

---

## Title

`fix(chat): direction-based stick-to-bottom — follow reliably, release on one wheel notch`

---

## Summary

### Problem

Auto-follow had two opposite-looking failure modes with **one root cause**: user
intent was inferred from distance-to-bottom, which cannot distinguish

- "the smooth follow lerp is lagging behind a growing stream", from
- "the user deliberately scrolled away".

Both look like *far from the bottom*. So the threshold is unwinnable:

- large enough to absorb lerp lag (`max(300, 1.5 viewports)`) makes follow
  reliable but **unescapable** — a wheel notch moves less than the slack, and the
  next content growth re-pins
- tight enough to release on a wheel notch **breaks following** mid-stream

The existing `autoScrollEnabled` flag provided no signal either: set `true` at
submit and never cleared, it was a dead gate.

### Fix

Replace the inference with an explicit `isPinned` intent flag driven by scroll
**direction**, which is unambiguous: *content growth never decreases `scrollTop`
— only the user scrolling up does.*

- **Unpin** on upward movement more than `REPIN_DISTANCE` (60px) off the bottom.
  The epsilon keeps prune/eviction scroll compensation — which lands back at the
  bottom — from reading as user intent.
- **Unpin immediately on wheel-up.** The wheel event fires *before* the scroll
  event, which wins the same-frame race against a growth re-pin.
- **Re-pin** when the user returns within 60px of the bottom. Direction-based
  implementations pair gesture unpinning with a small at-bottom epsilon;
  react-virtuoso's `atBottomThreshold` defaults to 4px.
- A **stick observer** (`MutationObserver` + per-child `ResizeObserver`) re-pins
  through late growth the lerp misses: image decode replacing a skeleton,
  syntax-highlight reflow, the final streamed block, the Thinking overlay
  transition. It defers while the lerp is actively animating.
- The lerp defers to `isPinned` each frame and carries **no distance drift
  guard**, so a mid-stream wheel-up stops it on the next frame rather than
  fighting the user.

The last point is the one to review: removing the drift guard is what makes the
release feel immediate, and it is safe precisely because `isPinned` is now an
explicit flag rather than a distance estimate.

---

## Verification

**12 passed** in the static direction/epsilon/observer suite, measured
2026-08-03. The branch also carries a `node --test` suite of 5 structural guards
on the lerp (`tests/streaming/autoscroll-threshold.test.mjs`).

---

## Scope

`static/js/ui.js` (+95/-6), 3 lines of CSS, two test files.
