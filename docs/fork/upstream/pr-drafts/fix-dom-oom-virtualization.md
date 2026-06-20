# PR Draft: fix/dom-oom-virtualization → pewdiepie-archdaemon/odysseus:dev

**Branch:** `jdmanring/odysseus:fix/dom-oom-virtualization`
**Issue:** [#2](https://github.com/jdmanring/odysseus/issues/2) (fork tracking)
**Status:** Two commits. File upstream issue first, then open PR.
- `31d0bbb5` — initial virtualization module
- `c1f399f5` — Phase 3 fix: message-count BIDI cap in `_loadOlder` (scroll-jump bug for agent sessions)

---

## Upstream PR title

`fix(dom): virtual message window to prevent renderer OOM on long sessions`

---

## Summary

### Problem

`#chat-history` renders every message in a session unconditionally. On session
open, `sessions.js` loops through the full history and calls `addMessage()` for
every message. During an active session, `addMessage()` appends new nodes but
nothing ever removes them. This has two concrete failure modes:

**Load crash**: A session with 300+ messages at ~3 DOM nodes each lands 900+
nodes in a single synchronous render. Agent-mode sessions produce 5–7 nodes per
message (role header, thinking block, content, tool-call panel, tool-result
panel); a 150-turn agent session produces 900–1050 nodes. All nodes are live
and held by the DOM tree; the GC correctly retains them all. The renderer
process exhausts its memory allocation on fully-live objects and crashes before
the page is interactive. Users experience a blank white screen on open.

**Accumulation crash**: A session that starts short grows OOM during a long
agentic run. No mechanism exists to reclaim nodes once they are appended.

Both failure modes are consistently reproducible. In my testing they occur at
~600 standard messages or ~150 agent turns on a 16 GB RAM machine with Chrome
running alongside other applications; the threshold is lower on constrained
machines.

The entire point of running Odysseus locally is extended, persistent conversations:
coding sessions, research threads, agent runs that span many tool calls. A user
working with a coding agent for two hours will have 200+ messages easily, and these
are exactly the sessions where an OOM crash is most disruptive.

The problem is worse on constrained hardware, which is common in this audience. Users
who self-host LLMs often run Odysseus on 8 GB RAM laptops, mini PCs, ARM SBCs, or
machines that are also running the inference stack itself (which consumes several GB of
RAM or unified memory). The 16 GB baseline above is the comfortable case; the actual
OOM threshold will be lower on machines with less RAM or more competing processes.

Agent mode compounds this further. A multi-step coding task produces 5–7 DOM nodes per
message round (role header, thinking block, content, tool-call panel, tool-result panel,
metadata row). A 150-turn agent session produces 900–1050 nodes — the same node count
as 300 standard user/model turns. The users who push agent mode hardest are the most
likely to hit OOM.

When the renderer crashes mid-stream, the in-progress model response is lost. The
`resumeStream` path in `chat.js` can replay the SSE buffer from the server, but the
buffer is bounded; a long response that was actively streaming when the crash hit may be
partially or fully missing on reload. No mechanism exists to re-request the cut-off
portion. The user must prompt again from scratch, consuming more rounds of an active
agent session or losing context.

### Solution

This PR introduces `static/js/chatHistory.js`, a ~730-line DOM virtualization
module that keeps the number of live DOM nodes bounded at all times, and
integrates it as a drop-in replacement for the existing `addMessage` for-loop
in `sessions.js`.

The implementation has three phases:

**Phase 1: Load-time windowing.**  
`window.chatHistory.load(messages)` renders only the most recent `WINDOW_SIZE`
(50) messages on session open. An `IntersectionObserver` watches a sentinel
element at the top of the list; scrolling up to the sentinel triggers
`_loadOlder()`, which prepends a `BATCH_SIZE` (25) message batch. Scroll
position is preserved by capturing `scrollHeight` before and after the insert
and adjusting `scrollTop` by the difference; preventing the viewport jump that
`insertBefore` would otherwise cause.

**Phase 2: Live pruning.**  
A `MutationObserver` watches `#chat-history` for `childList` changes. When
total non-control DOM children exceed `PRUNE_AT` (80) and the user is at the
scroll bottom, `_pruneTop()` removes the oldest `PRUNE_COUNT` (20) historical
nodes and inserts a height-matched `.chat-history-spacer` div in their place.
The spacer preserves scroll geometry; `scrollHeight` is unchanged so `scrollTop`
needs no adjustment. The pruned content is reachable again by scrolling up past
the sentinel. Phase 2 does not fire during `load()`: a `_loading` flag holds
it off through the initial render (a 50-message agent session produces ~250
nodes, far above `PRUNE_AT`).

**Phase 3: Bidirectional pruning.**  
When the user scrolls up and `_loadOlder()` pushes historical *messages* past
`BIDI_MSG_CAP` (80), the oldest loaded messages (just above `_histSep`) are
removed and a "↓ N earlier messages" bottom sentinel is inserted. Scrolling
down to the bottom sentinel (or clicking it) calls `_loadNewer()` to restore
the content, chaining until the full historical window is reloaded or the live
section is reached.

The cap is deliberately message-count based (`_endIdx - _startIdx`), not DOM-
node-count based. Multi-round agent messages produce 5–20 top-level DOM children
each; the WINDOW_SIZE=50 initial load can produce 500+ nodes before the first
`_loadOlder()` call. A DOM-node cap of 120 would prune 400+ nodes on the very
first upward scroll, collapsing `scrollHeight` by far more than the prepend added
and clamping `scrollTop` toward the bottom — the "scroll up, land at bottom"
failure mode reported for long agent sessions.

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

**`static/js/chatHistory.js`** (new, ~730 lines)  
The virtualization module. Runs as a plain (non-module) `<script>` tag so
`window.chatHistory` is available before any ES module import runs. The module
is entirely self-contained; it has one external dependency (`window.chatModule
.addMessage`) and exposes two public methods: `reset()` and `load(messages)`.

**`static/js/sessions.js`** (~15 lines changed)  
Before clearing `#chat-history.innerHTML`, call `window.chatHistory.reset()`.
Replace the `msgHistory.forEach(addMessage)` loop with
`window.chatHistory.load(_preparedMsgs)`. Move `scrollHistoryInstant()` to
after the post-load `hljs` pass: `overflow-anchor: none` disables Chrome's
automatic `scrollTop` compensation, so any DOM height increase after a manual
scroll (e.g., hljs expanding a code block above the viewport) leaves the user
short of the actual bottom. Calling `scrollHistoryInstant()` last ensures it
reflects the final, fully-laid-out height.

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

**`static/style.css`** (1 block, 6 lines)

- `.chat-history-sentinel`, `.chat-history-bottom-sentinel`, `.chat-history-spacer`
  all get `overflow-anchor: none`: Chrome's scroll-anchor algorithm
  automatically adjusts `scrollTop` when content is prepended above the
  viewport. `chatHistory.js` also adjusts `scrollTop` to compensate for
  prepended nodes. Without this rule, both fire on the same prepend and the
  scroll position jumps twice as far. The sentinels and spacer are the only
  elements that participate in virtual scroll mechanics; setting the property
  only on them avoids touching the broader scroll container.

### Implementation notes

**Why does `load()` attach the sentinel before scrolling?**  
The original order was: scroll then attach sentinel. `overflow-anchor: none`
means the 34 px sentinel height is not auto-compensated into `scrollTop`, so
the user ended up 34 px above the actual bottom. By attaching the sentinel
first, the single `this._c.scrollTop = this._c.scrollHeight` call at the end
of `load()` accounts for the sentinel's height in one shot. (IntersectionObserver
callbacks are asynchronous; they never fire within the same JS task, so there
is no risk of the observer triggering `_loadOlder()` before the scroll sets the
sentinel out of view.)

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

## Checklist

- [x] I searched [open issues](https://github.com/pewdiepie-archdaemon/odysseus/issues) and [open PRs](https://github.com/pewdiepie-archdaemon/odysseus/pulls); this is not a duplicate.
- [x] This PR targets `dev`
- [x] My changes are limited to the scope described above; no unrelated refactors or whitespace changes mixed in.
- [x] I actually ran the app (`docker compose up` or `uvicorn app:app`) and verified the change works end-to-end. Type-checks and unit tests are not enough.
- [ ] **I am not an LLM agent submitting a bulk PR.** I reviewed and tested this change personally before submitting.

## How to Test
Verified manually on Linux (Artix Linux, Wayland, NVIDIA open drivers) running in the
native Qt desktop wrapper (PyQt6 / QWebEngineView, Chromium-based). QtWebEngine has
tighter compositor timing than standalone Chrome, which made scroll-position races more
visible and drove several of the correctness fixes (the `_draining` flag, the double-rAF
snap, the settling loop). All scenarios below were exercised directly.

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

**Phase 2: Live pruning**
- Open 50-message agent session; exchange 10 user+model turns → historical nodes
  exceed PRUNE\_AT; oldest historical nodes pruned; height-matched spacer
  appears above remaining history; scroll position does not jump
- Scroll up through spacer to sentinel → spacer removed; historical batch
  prepended; scroll position stable
- Phase 2 does not fire during initial load of a 50-message agent session
  (would otherwise immediately prune 250 nodes > PRUNE\_AT)

**Phase 3: Bidirectional pruning**
- Session with 200 messages; scroll to first message; scroll back down →
  historical messages cap at BIDI\_MSG\_CAP (80); bottom sentinel appears;
  "↓ N earlier messages" count is accurate
- Click bottom sentinel → batch loads; chaining continues to live section
- Scroll back down without clicking → scroll listener triggers load at
  BIDI\_MARGIN (200 px) ahead of sentinel
- Agent session with 200+ messages (many tool rounds): scroll up → no visible
  jump to bottom on the first or subsequent batches (this was the scroll-jump
  regression caused by the DOM-node cap; use a heavy agent session to verify)

**Session switching**
- Rapid switch across 5 sessions → each session loads correctly; no content
  bleed-through from previous session; no stuck "loading" state
- Switch session while `_loadNewer()` chaining rAF is pending → new session
  unaffected (generation counter)

**Crash recovery (chat.js resumeStream)**
- Kill renderer mid-stream via `chrome://kill`; page reloads; `resumeStream`
  replays SSE buffer → thinking tokens render in collapsible block, not as
  visible text

**Scroll position on session open**
- Session with code blocks → opens exactly at bottom (last message fully
  visible); scrollHistoryInstant() fires after hljs so code-block expansion
  above viewport does not leave user short of bottom
- Click scroll-to-bottom button while any content is unloaded → reaches live
  section; bottom sentinel disappears

**Regression check; normal-length sessions**
- Sessions with 5, 15, 30 messages → all messages visible, no pagination UI,
  no spacer; behavior identical to pre-patch

**Automated tests.**  
`tests/test_chat_history_js.py` covers the virtualization state machine logic
(window sizing, sentinel management, index tracking, generation counter) using
a lightweight DOM stub; no browser required. `tests/test_chat_history_playwright.py`
covers the scroll behaviour end-to-end using Playwright. The existing pytest suite
covering backend endpoints is not affected by this change.

---



## Target branch

- [x] This PR targets **`dev`**, not `main`. All PRs land in `dev`; `main` is curated by the maintainer at each release.

## Linked Issue

Fixes # <!-- [file upstream issue first] -->

## Type of Change

- [x] Bug fix (non-breaking, fixes a confirmed issue)
- [ ] New feature (non-breaking, adds new behaviour)
- [ ] Breaking change (changes or removes existing behaviour)
- [ ] Refactor / cleanup (behaviour unchanged)
- [ ] Documentation only
- [ ] CI / tooling / configuration

## Filing Notes

1. **File upstream issue first**: draft in `docs/fork/upstream/issue-drafts/fix-dom-oom-virtualization.md`. Reference upstream reports #2869 and #3746 in the issue body (same root cause). Add the new issue number to `Fixes #` above before opening the PR. Do not ask to close #2869 or #3746: let maintainers decide.

2. No screenshot needed; fix is behavioral (OOM prevention), not visual. If reviewers ask: load a 600-message session from the DB; renderer crashes before this patch, loads cleanly after.

3. **Reviewer question to anticipate:** "Why not React virtualization libraries?" Answer: Odysseus uses plain HTML/JS with no bundler or framework. Vanilla JS with direct DOM manipulation, consistent with the rest of the codebase.

4. **Reviewer question to anticipate:** "Why include the chat.js resumeStream fix here?" Answer: The thinking-token bug only manifests when `resumeStream` replays a buffer after a crash; inseparable in practice from the crash-recovery path this PR introduces.

5. **Watch upstream discussion #929** (frontend framework migration). Virtualization logic is framework-agnostic; porting would be straightforward if needed.

## Visual / UI changes

This fix restructures how chat messages are stored in the DOM but does not
change their visual appearance. The virtualized implementation produces
identical output; same message bubbles, same layout, same scroll behavior
from the user's perspective. No before/after screenshot is meaningful.

Files changed that touch HTML, CSS, or JS:
- `static/index.html`: adds `<script src="chatHistory.js">` tag
- `static/js/chatHistory.js`: new virtualization module (DOM-writing)
- `static/js/chat.js`, `sessions.js`: delegate message management to the module
- `static/style.css`: adds `overflow-anchor: none` to 3 non-visible sentinel/spacer classes

None of the CSS additions are visible elements. No screenshot needed.
