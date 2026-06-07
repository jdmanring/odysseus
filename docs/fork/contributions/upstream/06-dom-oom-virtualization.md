# [UPSTREAM] DOM Virtualization — Fix Renderer OOM from Unbounded Chat History

## Status
- [x] Root cause confirmed with log evidence (2026-06-06)
- [x] Upstream issue filed: pewdiepie-archdaemon/odysseus #TBD
- [ ] Phase 1 implementation (load-time pagination)
- [ ] Phase 2 implementation (live pruning)
- [ ] Upstream PR opened

## Problem

Every chat message is appended to `#chat-history` as a live DOM node and never removed.
Two confirmed failure modes:

1. **Gradual accumulation during streaming** — a 20-round agent session generates 40+
   rich DOM subtrees (text bubbles, tool-call blocks) that fill the V8 Oilpan C++ heap.

2. **Bulk load on session open** — `selectSession()` renders the entire history at once,
   then `hljs.highlightElement()` runs on every code block. Confirmed OOM at only 78 MB
   after only 11 minutes on a fresh reload.

Log evidence (both crashes on same day, same machine):
```
[13269] V8 process OOM (Oilpan: Large allocation. Ran out of reservation) — 419 MB, 52 min
[13699] V8 process OOM (Oilpan: Large allocation. Ran out of reservation) — 78 MB, 11 min
```

## Secondary Bug (filed separately as #07)

`streamingTTS` declared `const` inside the `try` block (chat.js:1077) is referenced in
the `catch` block (line 2923). Causes `ReferenceError` on every stream error, aborting
the catch handler early.

## Proposed Fix

### Phase 1 — Load-time pagination (addresses bulk-load OOM)

`selectSession()` should render only the last N messages (e.g. 50) on load, store the
full history as plain JS objects, and use an IntersectionObserver on a sentinel element
at the top of `#chat-history` to prepend older messages on demand.

Scroll position preservation uses the `scrollHeight` delta technique:
```javascript
const before = chatHistory.scrollHeight;
// prepend messages...
chatHistory.scrollTop += chatHistory.scrollHeight - before;
```

### Phase 2 — Live session pruning (addresses streaming accumulation)

Cap `#chat-history` at ~80 DOM children. When exceeded, prune the oldest 20 nodes,
replace with a height-matched spacer div, and restore on scroll via IntersectionObserver.

### Phase 3 — streamingTTS scope fix (tracked separately in #07)

Hoist `let streamingTTS = false` before the `try` block at chat.js:604.

## Full Implementation Plan

See `personal_docs/plan-dom-virtualization.md` for full code sketches, file change table,
and testing checklist.

## Upstream Issue

Filed at: pewdiepie-archdaemon/odysseus — issue covers both crash modes with full log
evidence, code analysis, and the proposed fix.

## Notes

- No new dependencies required — IntersectionObserver is baseline-2019
- Fork-specific crash recovery (linux_wrapper.py renderProcessTerminated handler) already
  committed separately as a stopgap
- This fix benefits all users, not just Linux/Qt wrapper users
