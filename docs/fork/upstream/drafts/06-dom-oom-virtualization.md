# [UPSTREAM] Renderer OOM Crash from Unbounded Chat History DOM Growth

## Status
- Issue filed: Not yet filed
- PR opened: Not yet opened
- Fix in fork: **Applied to `develop`** (2026-06-08)
  - Crash recovery stopgap: committed (`linux_wrapper.py` `renderProcessTerminated` handler)
  - Phase 1 (load-time pagination): applied — `static/js/chatHistory.js`, `sessions.js`, `index.html`, `style.css`
  - Phase 2 (live pruning): applied — `chatHistory.js` `MessageWindow` live pruning + bidirectional pruning
  - **Blocker before filing:** screenshots per PR checklist (session with 200+ messages, scroll-up batch load, DevTools DOM count during agent run)

## Notes
This is a UI/frontend change touching `static/js/`. The upstream PR **requires screenshots**
of the chat interface showing the load-older sentinel and the windowed message display.
Attach screenshots before filing the PR. The fix must be verified by running a long
session (30+ rounds) and confirming the DOM child count stays bounded.

The crash recovery handler (`linux_wrapper.py`) is fork-specific (Qt wrapper only) and
must NOT be included in the upstream PR. Only the JS changes go upstream.

Phase 3 (streamingTTS scope fix) is tracked separately in `07-streamingtts-scope-fix.md`.

---

## Staged Issue
<!-- James: open https://github.com/pewdiepie-archdaemon/odysseus/issues/new?template=bug_report.yml and paste below -->

**Steps to Reproduce**

**Crash Mode 1 — Gradual accumulation:**

1. Start a long agent session with tool use (20+ rounds).
2. Each round generates multiple DOM nodes (user bubble, tool-call block, assistant bubble).
3. After ~40+ message nodes, the renderer crashes with a blank page.

**Crash Mode 2 — Bulk session load:**

1. Complete any chat session with 50+ messages.
2. Reload the page or switch to that session via the sidebar.
3. Renderer crashes immediately or within seconds of loading.

**Expected Behaviour**

The chat interface renders long sessions without crashing. Older messages are loaded
on demand rather than all at once.

**Actual Behaviour**

The renderer process crashes with a blank page. In browser DevTools / Chromium logs:

```
V8 process OOM (Oilpan: Large allocation. Ran out of reservation)
```

**Root Cause**

`#chat-history` accumulates every message as a live DOM node and never removes any.
Two distinct failure modes confirmed:

1. **Gradual accumulation during streaming** — 40+ rich DOM subtrees (text bubbles,
   tool-call blocks, syntax-highlighted code) exhaust the V8 Oilpan C++ heap's virtual
   address reservation. This is not a physical RAM issue — the GC freed 419 MB → 16 MB
   just before the fatal allocation, confirming it's a reservation limit.

2. **Bulk session load** — `selectSession()` at `sessions.js:1646` renders the entire
   session history in a single synchronous loop, then `hljs.highlightElement()` runs on
   every code block. A fixed-size Oilpan allocator pool is exhausted by the sudden burst.
   Confirmed crash at only 78 MB heap, 11 minutes after startup.

Log evidence (two crashes, same day):
```
[pid 13269] V8 process OOM (Oilpan: Large allocation. Ran out of reservation) — 419 MB, 52 min uptime
[pid 13699] V8 process OOM (Oilpan: Large allocation. Ran out of reservation) — 78 MB, 11 min uptime
```

Key source locations:
- `static/js/sessions.js` — `selectSession()` bulk-load loop (now replaced by `chatHistory.load()`)
- `static/js/chatRenderer.js:addMessage()` — appends to `#chat-history`, never removes
- `static/js/chat.js` — streaming path appends nodes, never prunes

**Proposed Fix**

**Phase 1 — Load-time pagination** (addresses bulk-load OOM):

`selectSession()` renders only the last 50 messages on load. Full history is stored as
plain JS objects. An `IntersectionObserver` on a sentinel element at the top of
`#chat-history` loads older messages in batches of 25 when the user scrolls up.

Scroll position is preserved using the `scrollHeight` delta technique:
```javascript
const before = chatHistory.scrollHeight;
// prepend messages...
chatHistory.scrollTop += chatHistory.scrollHeight - before;
```

**Phase 2 — Live DOM pruning** (addresses streaming accumulation):

Cap `#chat-history` at ~80 DOM children. When exceeded, prune the oldest 20 nodes,
replace with a height-matched spacer `<div>`, and restore them via `IntersectionObserver`
when the user scrolls to that spacer.

**No new dependencies required.** `IntersectionObserver` is baseline-available since 2019.

**Install Method:** Manual Python install (confirmed); Docker (not tested but same JS)

**OS:** Linux (Chromium renderer); expected to reproduce on any platform with long sessions

**Willing to submit a fix:** Yes — I can open a PR

---

## Staged PR
<!-- James: file the issue first, get the number, fill in Fixes #NNN below, then open PR -->

### Summary

Every chat message is appended to `#chat-history` as a live DOM node and never removed.
Long agent sessions (40+ messages) and bulk session loads both exhaust the V8 Oilpan
C++ heap, crashing the renderer to a blank page. Two confirmed OOM crashes on the same
day with full log evidence.

This PR adds a `MessageWindow` class that maintains a sliding window of DOM nodes
(~50 visible at a time). Older messages are stored as plain JS objects and rendered
on demand via `IntersectionObserver` as the user scrolls up. Live sessions prune the
oldest nodes from the DOM when the count exceeds 80, replacing them with height-matched
spacers. No new dependencies — `IntersectionObserver` is baseline-2019.

### Target branch
- [x] This PR targets **`dev`**, not `main`.

### Linked Issue

Fixes #

### Type of Change
- [x] Bug fix (non-breaking — fixes a confirmed issue)

### Checklist
- [x] Searched open issues and open PRs — not a duplicate
- [x] Targets `dev`
- [x] Changes limited to described scope — no unrelated refactors
- [ ] App run locally and fix verified end-to-end *(must do before filing — see How to Test)*

### How to Test

**Phase 1 — Load-time pagination:**
1. Create a session with 200+ messages (or use an existing long session).
2. Reload the page and select the session.
3. Confirm only the last ~50 messages render immediately (no crash).
4. Confirm a "↑ N earlier messages" sentinel appears at the top.
5. Scroll to the top — confirm the previous 25 messages prepend without the page jumping.
6. Continue scrolling up — confirm batches load until the sentinel disappears.
7. Send a new message — confirm it appends correctly at the bottom.

**Phase 2 — Live pruning:**
1. Start an agent task and let it run for 30+ rounds.
2. Open DevTools → Elements, count children of `#chat-history`.
3. Confirm the count stays at or below ~80 throughout the session.
4. Scroll to the top — confirm a height-matched spacer is visible and older messages
   load when scrolled to.

**Regression check:**
1. Switch between sessions — confirm `chatHistory.reset()` clears state correctly.
2. Start a fresh session (no history) — confirm normal message display.

### Visual / UI changes

- [x] This change affects what renders in `#chat-history` — screenshots required.
- [ ] Screenshot: session with 200+ messages showing load-older sentinel at top *(attach before filing)*
- [ ] Screenshot or clip: scrolling up to load older messages without page jump *(attach before filing)*
- [ ] Screenshot: agent session mid-run showing bounded DOM (DevTools Elements panel) *(attach before filing)*
- [x] Style match: sentinel uses existing CSS variables (`--fg`, `--border`), no new colors or fonts
- [x] No new component patterns — extends existing `addMessage` flow
- [x] No Unicode emoji in UI or code — sentinel uses plain text "↑ N earlier messages"
