# PR Draft: fix/dom-oom-virtualization → pewdiepie-archdaemon/odysseus:dev

**Branch:** `jdmanring/odysseus:fix/dom-oom-virtualization`
**Issue:** [#2](https://github.com/jdmanring/odysseus/issues/2) (fork tracking)
**Status:** Needs squash (4 commits → 1) before filing

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

**Hardening against live sessions (follow-up):**  
The original implementation had three bugs that only manifested once the user
and model started exchanging messages:

1. `_pruneTop` used `continue` at `_histSep` instead of `break`, letting the
   prune loop cross into live nodes (post-sep DOM with no `_all` entry).
2. `_startIdx` was advanced by raw DOM node count. Agent-mode messages produce
   5+ nodes each, so `_startIdx` overshot `_all.length`. `_loadOlder` then
   accessed `_all[167]` on a 50-message array → `TypeError` crash that locked
   the chat and made scroll stop working.
3. `_maybePrune` used `_liveChildCount()` which counts post-sep live nodes that
   can never be pruned, inflating the target and worsening bug 2.

Fixed by: `break` at `_histSep`; derive `_startIdx` from `data-ch-idx` (same
pattern `_loadNewer` already used); partial-message cleanup at the prune
boundary; switch `_maybePrune` to `_histChildCount()` with a null guard for
sessions where `load()` was never called.

Also fixes a thinking-token leak in `chat.js` `resumeStream`: the server sends
`{delta, thinking:true}` for reasoning tokens. The main handler wraps these in
`<think>…</think>` so `addMessage` renders them in a collapsible section.
`resumeStream` read `json.delta` without checking `json.thinking`, so raw
thinking content rendered as plain text in the replay bubble on crash-recovery
reload. Fixed by mirroring the main handler's `_thinkOpen` state machine,
stripping thinking blocks from intermediate `renderDelta` display, and closing
any unclosed block before finalization.

**Phase 2 live-node OOM gap:**  
`_maybePrune` used `_histChildCount()` as the prune threshold, which counts
only nodes before `_histSep`. Live nodes (appended after `_histSep` during the
active session) were never counted, so a session with many live turns
accumulated DOM nodes indefinitely. Fixed by using `_liveChildCount()` (total
non-control nodes) for the threshold while still capping the prune itself at
available historical nodes — live nodes have no `_all[]` entry and cannot be
safely removed.

**Phase 2 O(n) DOM walk on every streaming token:**  
`_initMutObs` called `_maybePrune` directly on each MutationObserver fire.
During active streaming (one fire per token append) this ran an O(n) DOM walk
per frame. Fixed with a `_prunePending` rAF guard that collapses all mutations
within one animation frame into a single prune check.

**Compositor flicker on sidebar/dropdown hover:**  
`.chat-container` carried `will-change: transform; transform: translateZ(0);`
which promoted it to a GPU compositor layer. The sidebar and dropdown menus use
`backdrop-filter: blur()` and sample their backdrop from whatever is behind
them; when `chat-container` is its own GPU texture, Chrome flushes that texture
on any hover/state change, producing a 1-2 frame black-screen flash on menu
open/close and sidebar element hover. Fixed by removing the GPU promotion hints
from `.chat-container` — the `margin-left/right` transition does not require
them.

**Chrome scroll-anchor double-compensation:**  
`.chat-history` lacked `overflow-anchor: none`. Chrome's automatic scroll
anchoring adjusted `scrollTop` when `_loadOlder` prepended historical batches,
then the manual `scrollTop +=` compensation in `_loadOlder` also ran, causing
the viewport to jump twice the intended distance. Fixed by setting
`overflow-anchor: none` on the container so only the manual adjustment fires.

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

1. Squash the 4 commits on this branch to 1 before opening the PR.
2. No screenshot required — the fix is behavioral (OOM prevention + crash
   recovery), not visual. If upstream asks for evidence, offer to reproduce the
   crash on an unpatched build or point to the memory growth mechanics in the
   code.
3. File issue on `pewdiepie-archdaemon/odysseus` first; add its number here
   before opening the PR.
