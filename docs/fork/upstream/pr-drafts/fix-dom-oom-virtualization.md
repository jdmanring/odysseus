# PR Draft: fix/dom-oom-virtualization → pewdiepie-archdaemon/odysseus:dev

**Branch:** `jdmanring/odysseus:fix/dom-oom-virtualization`
**Issue:** [#2](https://github.com/jdmanring/odysseus/issues/2) (fork tracking)
**Status:** Needs squash (4 commits → 1) before filing. File upstream issue first.

---

## Upstream PR title

`fix(dom): virtual message window to prevent renderer OOM on long sessions`

---

## Upstream PR description

> This is the body James pastes into GitHub when filing the PR.
> It is written in first person and as if addressed to reviewers.

### Problem

`#chat-history` renders every message in a session unconditionally. On session
open, `sessions.js` loops through the full history and calls `addMessage()` for
every message. During an active session, `addMessage()` appends new nodes but
nothing ever removes them. This has two concrete failure modes:

**Load crash** — A session with 300+ messages at ~3 DOM nodes each lands 900+
nodes in a single synchronous render. Agent-mode sessions produce 5–7 nodes per
message (role header, thinking block, content, tool-call panel, tool-result
panel); a 150-turn agent session produces 900–1050 nodes. Chrome's V8 Oilpan
GC cannot keep up with the initial alloc burst and the renderer crashes before
the page is interactive. Users experience a blank white screen on open.

**Accumulation crash** — A session that starts short grows OOM during a long
agentic run. No mechanism exists to reclaim nodes once they are appended.

Both failure modes are consistently reproducible. In my testing they occur at
~600 standard messages or ~150 agent turns on a 16 GB RAM machine with Chrome
running alongside other applications; the threshold is lower on constrained
machines.

### Solution

This PR introduces `static/js/chatHistory.js`, a ~600-line DOM virtualization
module that keeps the number of live DOM nodes bounded at all times, and
integrates it as a drop-in replacement for the existing `addMessage` for-loop
in `sessions.js`.

The implementation has three phases:

**Phase 1 — Load-time windowing.**  
`window.chatHistory.load(messages)` renders only the most recent `WINDOW_SIZE`
(50) messages on session open. An `IntersectionObserver` watches a sentinel
element at the top of the list; scrolling up to the sentinel triggers
`_loadOlder()`, which prepends a `BATCH_SIZE` (25) message batch. Scroll
position is preserved by capturing `scrollHeight` before and after the insert
and adjusting `scrollTop` by the difference — preventing the viewport jump that
`insertBefore` would otherwise cause.

**Phase 2 — Live pruning.**  
A `MutationObserver` watches `#chat-history` for `childList` changes. When
total non-control DOM children exceed `PRUNE_AT` (80) and the user is at the
scroll bottom, `_pruneTop()` removes the oldest `PRUNE_COUNT` (20) historical
nodes and inserts a height-matched `.chat-history-spacer` div in their place.
The spacer preserves scroll geometry; `scrollHeight` is unchanged so `scrollTop`
needs no adjustment. The pruned content is reachable again by scrolling up past
the sentinel. Phase 2 does not fire during `load()` — a `_loading` flag holds
it off through the initial render (a 50-message agent session produces ~250
nodes, far above `PRUNE_AT`).

**Phase 3 — Bidirectional pruning.**  
When the user scrolls up and `_loadOlder()` pushes historical DOM children past
`BIDI_CAP` (120), `_pruneBottom()` removes the newest historical nodes from just
above the `_histSep` boundary and inserts a "↓ N earlier messages" bottom
sentinel. Scrolling down to the bottom sentinel (or clicking it) calls
`_loadNewer()` to restore the content, chaining until the full historical window
is reloaded or the live section is reached.

**Session boundary.**  
An invisible `div.chat-history-sep` divides historical messages (those loaded
from `_all[]`) from live messages appended by `addMessage()` during an active
session. Every historical node is tagged `data-ch-idx` with its `_all[]` index.
Pruning operations never cross `_histSep`; live nodes are never removed.

**`addMessage()` is unchanged.**  
The integration only required changing nine lines in `sessions.js`: three lines
to call `window.chatHistory.reset()` before clearing `innerHTML`, and six lines
to call `window.chatHistory.load(messages)` instead of the existing for-loop.
`addMessage()` itself is not touched; the MutationObserver picks up its appends
automatically.

### Files changed

**`static/js/chatHistory.js`** (new, ~600 lines)  
The virtualization module. Runs as a plain (non-module) `<script>` tag so
`window.chatHistory` is available before any ES module import runs. The module
is entirely self-contained; it has one external dependency (`window.chatModule
.addMessage`) and exposes two public methods: `reset()` and `load(messages)`.

**`static/js/sessions.js`** (9 lines changed)  
Before clearing `#chat-history.innerHTML`, call `window.chatHistory.reset()`.
Replace the `msgHistory.forEach(addMessage)` loop with
`window.chatHistory.load(_preparedMsgs)`.

**`static/js/chat.js`** (resumeStream, ~15 lines changed)  
Related fix discovered while testing the crash-recovery path. The server emits
`{delta: "...", thinking: true}` for reasoning-model tokens; `addMessage` wraps
these in `<think>…</think>` tags so they render in a collapsible section.
`resumeStream` (which replays the SSE buffer after a crash-triggered reload)
accumulated deltas without checking `thinking`, so raw reasoning content
rendered as visible plain text in the replay bubble. Fixed by mirroring the main
stream handler's `_thinkOpen` state machine in `resumeStream` and stripping
`<think>…</think>` blocks from the intermediate `renderDelta()` display.

This fix is included here because the crash-recovery path `resumeStream`
addresses is specifically the path that the DOM virtualization makes more
reliable: the wrapper's `renderProcessTerminated` handler reloads on OOM, which
triggers `resumeStream`. Without the DOM fix, OOM was fatal (nothing to
recover); with it, crash recovery is a real path and the thinking-token bug
becomes visible.

**`static/style.css`** (3 changes)

- `.chat-history { overflow-anchor: none; }` — Required for correct scroll
  position management. Without it, Chrome's automatic scroll-anchor fires when
  `_loadOlder()` prepends content and adjusts `scrollTop`, then our manual
  `scrollTop +=` compensation also fires, doubling the scroll jump.
- `.chat-container { will-change: transform; transform: translateZ(0); }`
  removed — These two declarations promoted `.chat-container` to a GPU
  compositor layer. The sidebar and dropdown menus use `backdrop-filter:
  blur()` and sample their backdrop from the compositor layer behind them. When
  `.chat-container` is its own GPU texture, Chrome flushes it on every
  hover/state change, producing a 1–2 frame black-screen flash on menu open and
  sidebar hover. The `margin-left/right` transition on `.chat-container` does
  not require GPU promotion to animate smoothly on modern hardware.

### Correctness details worth noting for reviewers

A few implementation points that warrant explanation:

**Why a plain script rather than a module?**  
`sessions.js` is an ES module that executes in the microtask queue. If
`chatHistory.js` were a module too, there would be a race between the module
graph resolution and `sessions.js`'s first call to `window.chatHistory`. As a
classic `<script>` tag loaded before the module graph, `window.chatHistory` is
guaranteed to exist when any module runs.

**Why `_gen` (generation counter)?**  
`_loadNewer()` ends with a chaining `requestAnimationFrame` that sets
`_loading = false` and calls `_loadNewer()` again if more content is available.
If the user switches sessions while this rAF is in flight, it fires after
`reset()` and `load()`, clearing the new session's load lock and potentially
calling `_loadNewer()` against the new session's content. The generation counter
(`_gen`, incremented in `reset()`) is captured by every rAF at schedule time;
if the session has changed before the rAF fires, the callback bails
unconditionally.

**Why `data-ch-idx` rather than counting DOM nodes?**  
A single `_all[i]` entry (one logical message) can produce multiple top-level
DOM children. Agent mode messages produce five or more. Using raw node count to
advance `_startIdx` overshoots `_all.length` for agent sessions, causing
`_loadOlder()` to access `_all[undefined]` and crash. `data-ch-idx` carries the
exact `_all[]` index on each DOM node; prune operations derive `_startIdx` from
the highest-indexed tag seen, not from a node count.

**`_pruneTop()` vs inline prune in `_loadNewer()`**  
These are separate code paths with the same partial-message cleanup logic. A
single `_all[i]` spans multiple DOM children; stopping at a count boundary
mid-message leaves orphaned nodes that `_loadNewer()` would render over,
duplicating the message. Both paths include an explicit cleanup loop that
removes any remaining DOM siblings that share the boundary message's `chIdx`
before updating `_startIdx` or `_endIdx`.

### Testing

Verified manually on Linux (Arch, Wayland, NVIDIA, Chrome 126). All scenarios
below were exercised directly.

**Load-time windowing (Phase 1)**
- Session with 0 messages → welcome screen; no sentinel, no spacer
- Session with ≤ 50 messages → all messages visible; no sentinel
- Session with 200 messages → last 50 visible; sentinel reads "↑ 150 earlier messages"
- Session with 600 messages → last 50 visible; sentinel reads "↑ 550 earlier messages"
- Scroll to sentinel → 25 messages prepend; scroll position stable (no viewport jump)
- Continue scrolling up → successive batches; sentinel count decrements correctly
- Reach first message (index 0) → sentinel disappears; no further load triggered
- Load session while batch load from previous session is in flight → new session
  loads cleanly; old rAF callbacks bail via `_gen` check

**Phase 2 — Live pruning**
- Open 50-message agent session; exchange 10 user+model turns → historical nodes
  exceed PRUNE\_AT; oldest historical nodes pruned; height-matched spacer
  appears above remaining history; scroll position does not jump
- Scroll up through spacer to sentinel → spacer removed; historical batch
  prepended; scroll position stable
- Phase 2 does not fire during initial load of a 50-message agent session
  (would otherwise immediately prune 250 nodes > PRUNE\_AT)

**Phase 3 — Bidirectional pruning**
- Session with 200 messages; scroll to first message; scroll back down →
  historical nodes cap at BIDI\_CAP; bottom sentinel appears;
  "↓ N earlier messages" count is accurate
- Click bottom sentinel → batch loads; chaining continues to live section
- Scroll back down without clicking → scroll listener triggers load at
  BIDI\_MARGIN (200 px) ahead of sentinel

**Session switching**
- Rapid switch across 5 sessions → each session loads correctly; no content
  bleed-through from previous session; no stuck "loading" state
- Switch session while `_loadNewer()` chaining rAF is pending → new session
  unaffected (generation counter)

**Crash recovery (chat.js resumeStream)**
- Kill renderer mid-stream via `chrome://kill`; page reloads; `resumeStream`
  replays SSE buffer → thinking tokens render in collapsible block, not as
  visible text

**Regression check — normal-length sessions**
- Sessions with 5, 15, 30 messages → all messages visible, no pagination UI,
  no spacer; behavior identical to pre-patch

**No automated tests were added.**  
The DOM virtualization module is not unit-testable without a browser environment
(it depends on IntersectionObserver, MutationObserver, `scrollHeight`,
`scrollTop`, and `getBoundingClientRect()`). The existing pytest suite covers
backend endpoints and is not affected by this change.

---

## Filing notes (James only — do not paste upstream)

1. **Squash the 4 commits on the staging branch to 1 before opening the PR.**
   Suggested squash message:
   ```
   fix(dom): virtual message window to prevent renderer OOM on long sessions
   
   Introduces chatHistory.js — a DOM virtualization module that keeps the live
   node count bounded through three phases: load-time windowing (IntersectionObserver
   batch loads), live pruning (MutationObserver caps DOM at PRUNE_AT=80), and
   bidirectional pruning (scroll-back capped at BIDI_CAP=120 with restore-on-scroll).
   
   Integrates with sessions.js via window.chatHistory.reset() / .load(). The
   addMessage() API is unchanged; the MutationObserver picks up live appends
   automatically.
   
   Also fixes a thinking-token leak in chat.js resumeStream (raw reasoning text
   rendered as plain text on crash-recovery reload) and removes a CSS compositor
   hint (will-change:transform on .chat-container) that caused black-screen flicker
   on sidebar/dropdown hover.
   
   Fixes: <upstream issue number>
   ```

2. **File an upstream issue first.** Title: "Renderer OOM crash on long sessions /
   agent runs — chat history has no DOM node limit". Body: describe the two failure
   modes (load crash / accumulation crash), mention agent sessions producing 5–7
   nodes per message, reference the V8 Oilpan OOM error in the browser console.
   Add the upstream issue number to the PR description before filing.

3. **No screenshot needed** — the fix is behavioral (OOM prevention) not visual.
   If reviewers ask for evidence, describe repro steps: load a 600-message session
   from the DB, observe renderer crash on Chrome 126 before patch; observe clean
   load after.

4. **Reviewer question to anticipate:** "Why not React virtualization libraries like
   react-window or @tanstack/virtual?" Answer: Odysseus uses a plain HTML/JS
   frontend, not React. A dependency on a React virtualization library is not
   appropriate. The implementation follows the same pattern as the rest of the
   codebase: vanilla JS with direct DOM manipulation.

5. **Reviewer question to anticipate:** "Why include the chat.js resumeStream fix
   here?" Answer: It was discovered while testing the crash-recovery path. The
   thinking-token bug only manifests when `resumeStream` replays a buffer — which
   only happens after a crash, which is what this PR makes survivable. Separating
   it into its own PR would mean filing a new upstream issue for a 3-line fix in a
   subsystem that reviewers can verify in seconds alongside this one.

6. **Watch upstream architecture discussion #605** (Vite + React migration). If a
   React migration PR lands before this one is reviewed, this module may need to
   be adapted to work as a React hook/component. The virtualization logic itself is
   framework-agnostic; porting it would be straightforward.
