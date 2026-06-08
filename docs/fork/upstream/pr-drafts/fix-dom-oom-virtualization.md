# PR Draft: fix/dom-oom-virtualization → pewdiepie-archdaemon/odysseus:dev

**Branch:** `jdmanring/odysseus:fix/dom-oom-virtualization`
**Issue:** [#2](https://github.com/jdmanring/odysseus/issues/2) (fork tracking)
**Status:** Needs squash (2 commits → 1) before filing

---

## Title

`fix(dom): virtual message window to prevent renderer OOM on long sessions`

---

## Description

### Problem

Odysseus loads all messages of a chat session into the DOM at once on session
open, and `addMessage()` appends nodes without ever removing them. On long
sessions — particularly agentic runs with many tool calls, each of which
produces multiple child elements — this causes V8 Oilpan OOM crashes in the
browser renderer:

- **Load crash:** session with several hundred messages renders thousands of DOM
  nodes synchronously on open. Renderer runs out of memory before the page is
  interactive.
- **Accumulation crash:** session starts clean but grows OOM during a long
  agentic run as `addMessage()` keeps appending. No mechanism exists to trim
  the live DOM.

### Fix

Introduces `static/js/chatHistory.js` — a DOM virtualization module that
exposes a `window.chatHistory` API used by the session loader instead of the
previous `addMessage` for-loop.

**Phase 1 — Load-time windowing:**  
On session load, only the most recent `WINDOW_SIZE=50` messages are rendered.
An `IntersectionObserver` watches a sentinel element at the top of the list;
scrolling up triggers `_loadOlder()`, which prepends `BATCH_SIZE=25` messages
at a time. Scroll position is preserved via `scrollHeight` delta so the
viewport doesn't jump.

**Phase 2 — Live pruning:**  
A `MutationObserver` counts non-control DOM children after each append. When
the count exceeds `PRUNE_AT=80`, `_pruneTop()` removes the oldest
`PRUNE_COUNT=20` nodes and replaces them with a height-matched
`.chat-history-spacer` div so scroll geometry is preserved.

**Phase 3 — Bidirectional pruning:**  
When a user scrolls far back through historical content, the bottom of the
historical section is pruned once historical DOM children exceed `BIDI_CAP=120`.
A bottom sentinel restores pruned content when the user scrolls back down.

All three phases share a `_loading` lock so Phase 2 pruning cannot fire during
the initial render of a freshly-loaded session (an agent session of 50 messages
× ~5 DOM children each would otherwise immediately exceed `PRUNE_AT`).

**Session integration:**  
`sessions.js` calls `window.chatHistory.reset()` before clearing
`#chat-history` and `window.chatHistory.load(messages)` to render on session
open, passing the full message list. `addMessage()` is unchanged — the
`MutationObserver` picks up its appends automatically.

### Behavior

To the user the experience is unchanged: the most recent messages are visible,
scrolling up fetches older ones, and "N earlier messages" sentinels indicate
omitted content. No visual regression in normal-length sessions.

### Testing

- Manual: sessions with 50, 150, 300, and 600+ messages; scroll-up batch
  loading; live append during agentic run; bidirectional scroll; page reload
  mid-session.
- No automated tests added (DOM virtualization is difficult to unit-test without
  a real browser; the implementation is well-guarded with the `_loading` flag
  and explicit sentinel/spacer handling).

---

## Filing Notes (James)

1. Squash the 2 commits on this branch to 1 before opening the PR.
2. No screenshot required — the fix is behavioral (OOM prevention), not visual.
   If upstream asks for evidence, offer to reproduce the crash on an unpatched
   build or point to the memory growth mechanics in the code.
3. File issue on `pewdiepie-archdaemon/odysseus` first; add its number here
   before opening the PR.
