# PR Draft: perf/streaming-final-render -> odysseus-dev/odysseus:dev

**Branch:** `perf/streaming-final-render`
**Status:** Ready to file
**Base:** cut from `upstream-mirror`, 2 files, +98/-1

---

## Title

`perf(streaming): skip the final innerHTML re-render for plain responses`

---

## Summary

### Problem

When a stream completes, the `[DONE]` handler re-renders the whole message via
`innerHTML`. For a response with no thinking blocks, no sources and no findings,
**the streaming renderer already holds exactly the correct final content** — so
that re-render rebuilds identical markup and detaches the entire subtree it just
replaced.

The cost lands at the worst moment: the end of a long response, when the message
is at its largest, and it produces a detached DOM subtree proportional to the
whole message for zero visible change.

### Fix

For the plain case only: call `finalize()` to freeze the remaining tail in place,
then unwrap the `stream-content` div. Same resulting DOM, without constructing
and discarding a copy of it.

**Four guard conditions** decide "plain" (no thinking blocks, no sources, no
findings, and the renderer present). Any of them failing takes the existing
full-rerender path, unchanged — the sources/findings rendering is not touched by
this PR.

**Degraded mode preserved:** if `_streamRenderer` is absent, the full re-render
runs exactly as today. That fallback is what makes the optimisation safe to take
on the fast path.

---

## Verification

**7 passed**, measured 2026-08-03. The static tests pin all four guard
conditions, that `finalize()` is called before the null, that children are moved
before `stream-content` is removed (order matters — the reverse loses them), the
degraded-mode fallback, and that the existing full-rerender path is unchanged.

---

## Scope

`static/js/chat.js` (+16/-1) and one test file.
