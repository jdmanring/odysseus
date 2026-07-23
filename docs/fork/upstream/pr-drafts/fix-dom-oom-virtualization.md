> **⚠️ NOT FILE-READY.** The maintainer's own history pager (commit `45ee5a71`) owns
> the history render + scroll path; this PR offers the `MessageWindow` as the fuller
> alternative, with the prerequisite route-shadow fix staged separately as
> `fix/history-route-shadow` (#125, draft `fix-history-route-shadowing.md`). The earlier
> eviction-graft branch `fix/chat-history-dom-eviction` was dropped 2026-07-22 — its graft
> was superseded by this PR's own eviction. This draft's body needs a full rewrite at file
> time (plan Part 5). Provenance: plan Part 1.2 is the only framing to use.
>
> **Branch hygiene before filing:** drop commit `b328e905` (a settings-keybind fix, byte-
> identical to `fix/settings-shortcut-resurrection` / #143) — it is unrelated scope creep
> that belongs to #143, not here.

# PR Draft — fix/dom-oom-virtualization

**Branch**: `fix/dom-oom-virtualization` (from `upstream-mirror`)
**Issue**: jdmanring/odysseus#2
**Upstream issue**: file before filing PR
**Status**: Not yet submittable; the draft body needs a full rewrite at file time (plan
Part 5). Independent architecture, authored nine days before #4661 opened; #4661 is
parallel work on the same problem (plan Part 1.2).

---

## Title

`fix(dom): virtual message window — three-phase DOM cap to prevent renderer OOM on long sessions`

## Summary

The `#chat-history` element accumulates every message DOM node for the lifetime of a session with no bound. In a 308-message agent session this produces 50,000–200,000+ DOM nodes and 14–18 GB renderer RSS.

This PR introduces a three-phase DOM virtualization system in a new file (`static/js/chatHistory.js`) and wires it into `sessions.js`, `chat.js`, and `index.html`.

## Phase 1 — load-time windowing

On session load, only the last 50 messages (`WINDOW_SIZE`) are rendered. Older batches load on demand via `IntersectionObserver` as the user scrolls up (`BATCH_SIZE=25`). A double-rAF snap in `load()` lands at the true bottom after layout commit; an 8-frame settling loop re-snaps while `scrollHeight` grows from lazy images and web font loads. `img.onload` handlers catch burst-cache inflation that exceeds a single settling frame.

## Phase 2 — live pruning

A `MutationObserver` caps DOM children at `PRUNE_AT=80` during active streaming. `_pruneTop()` saves `scrollTop` before removal (the browser clamps it when `scrollHeight` shrinks) and restores it after inserting a height-matched spacer, eliminating the visible scroll jump on prune.

**Phase 2 also handles history exhaustion.** `_maybePrune()` previously hard-stopped when all historical messages had been pruned (`hist === 0`), permanently disabling Phase 2 for the rest of the session. The fix routes to `_evictLive(count)` instead:

- Removes the `count` oldest live DOM nodes (those immediately above the viewport when scrolled to bottom)
- Clears `_waveInterval` and `_elapsedTicker` (agent tool animation intervals) before removal
- Nulls `_streamRenderer` (holds `lastText` string in old-gen) before removal; recurses into descendants
- Compensates `scrollTop` for the removed nodes' height
- Shows an in-place notice: "↑ N earlier messages not shown — reload session to see all"

The evicted messages are persisted in the DB and reload normally on session switch.

## Phase 3 — bidirectional pruning

When the user scrolls up through loaded history, `_loadOlder()` caps the historical section at `BIDI_MSG_CAP=80` *messages* (not DOM nodes). Multi-round agent messages produce many top-level DOM children each, so a DOM-node cap at `BIDI_CAP=120` causes a massive prune on the first `_loadOlder()` call when `WINDOW_SIZE=50` messages are already loaded. A bottom sentinel + scroll listener drives `_loadNewer()`; a `_draining` flag bypasses QtWebEngine compositor lag on `scrollTop` read-back.

## Scroll fixes

- `scrollHistoryInstant()` moved after `hljs.highlightAll()` so the snap fires after code-block height is committed (`overflow-anchor:none` disables Chrome's automatic adjustment)
- Scroll-to-bottom button delegates to `chatHistory.scrollToBottom()`, which sets `_draining=true` and drains all `_loadNewer()` batches before settling at the true end of history

## CSS

- `overflow-anchor:none` on sentinel and spacer elements prevents the browser from double-compensating programmatic `scrollTop` assignments
- `will-change` removed from chat container and input bar elements that were promoting unnecessary compositor layers

## Per-node teardown

`_evictLive()` clears this app's own `_waveInterval`/`_elapsedTicker` handles before removing an element, releases `_streamRenderer` references, disconnects the IntersectionObserver, and releases hljs-defer references. #4661's `_trimChatHistoryDOM()` is not used: it destroys chatHistory.js control elements (sentinel, spacer, histSep).

## What was NOT done (and why)

Moving evicted live messages back into `_all[]` for Phase 1 reload was considered. Not implemented because:
1. Live messages have no `data-ch-idx`, making `_all[]` reconstruction ambiguous for multi-round agent responses
2. The user is at the bottom watching active messages; eviction targets are far above the viewport and already read

The simpler approach (evict + notice + reload via session switch) is sufficient for the OOM goal and avoids `_all[]` corruption.

## Related: edit/regenerate/fork correctness (#169)

Bounding the DOM makes visible a pre-existing bug this PR does **not** own and does **not** fix: edit/regenerate/fork derive the server `keep_count` from `indexOf('.msg')` (a DOM position), while the server treats it as an absolute DB index. That is wrong whenever the rendered set isn't the whole conversation from index 0 — which is true under this window layer, but was already true on upstream's own tail-page pager. This PR *reduces* the fresh-load blast radius (it renders up to `WINDOW_SIZE` messages, vs upstream's smaller page) but its eviction removes the "scroll to the very top and the indices line up" recovery path for very long plain conversations. The correct cure is orthogonal and shipped separately as an id-based truncate/fork (fork issue #169): it addresses messages by DB id, so it is independent of *how* the DOM is bounded. Keep the two PRs separate — #169 fixes an upstream bug and must land regardless of whether this window rewrite is adopted.

## Test plan

- `tests/test_chat_history_js.py`: 129 static-analysis tests
- `tests/test_chat_history_playwright.py`: 20 Playwright integration test functions
  (self-contained harness page; no running server needed) — includes runtime coverage of
  scroll-down windowing, the scroll-to-bottom drain/snap transition, and teardown
  (timers cleared + `hljsDeferForgetNode` called when pruning removes nodes)
- `tests/test_chat_history_a11y_js.py`: 8 accessibility contract tests
- `tests/test_chat_history_reset_before_wipe_js.py`: source-assertion guard that
  `chatHistory.reset()` precedes the `innerHTML=''` wipe in every chat-history
  clear path (New Chat, `/clear`, archived-view, group-chat start) — prevents the
  stale-counter regression from recurring
- `tests/test_chat_history_render_paging_playwright.py`: 5 end-to-end tests that boot the
  real app (uvicorn + seeded 300/2000-message sessions) and drive rendering, markdown
  mapping, server paging, the full deep-back walk, and DOM bounding against the live
  `/api/history` contract (skips with an explicit reason until the separately-staged
  route-shadowing fix unblocks the paginated endpoint)
- `tests/test_chat_history_longsession_playwright.py`: automated long-session soak — a
  local mock OpenAI-compatible server (`tests/bench/mock_llm.py`) streams SSE replies so
  the real send path runs end-to-end in headless Chromium for 55 exchanges; asserts every
  exchange completes, the DOM stays bounded across the live-prune threshold, auto-follow
  holds, both thinking indicators appear and clear, scroll-up walks back to the first
  message bounded, and scroll-to-bottom re-pins (~90s, no model required)
- Manual: run a long agent session (80+ exchanges) and confirm DOM child count stays bounded via `document.getElementById('chat-history').children.length` in the browser console
- Manual: confirm the eviction notice appears after enough exchanges and the text is correct
- Manual: confirm `scrollTop` does not jump when eviction fires
- Manual: confirm older messages reload correctly on session switch after eviction

## Files changed

- `static/js/chatHistory.js` — new file; full `MessageWindow` implementation
- `static/js/sessions.js` — map history through the existing display filters and hand
  `chatHistory.load()` a server-paging loader against the paginated `/api/history`
- `static/js/chat.js` — resume-think stream handling the windowed render path depends on
- `static/app.js` — header "· N msgs" counter reads `chatHistory.messageCount()` (server
  total + live messages) instead of counting DOM nodes, which undercounts once the DOM
  is windowed; the fallback DOM count excludes `.msg-continuation` rounds
- `static/js/keyboard-shortcuts.js` / `static/js/sessions.js` /
  `static/js/slashCommands.js` / `static/js/group.js` — every path that wipes
  `#chat-history` calls `chatHistory.reset()` first (the window layer's API
  contract), so a prior session's window state and message total don't survive
  onto the next screen. A repo-wide sweep of every `getElementById('chat-history')`
  acquisition confirmed all wipe sites are covered: session-select/load,
  delete-session, `createDirectChat` (New Chat), `_cmdSessionClear` (`/clear`),
  the archived-session view, and the group-chat start handler. Without it the
  header counter re-reads the stale `messageCount()` on the wipe and shows
  "New Chat · N msgs" on a fresh chat
- `static/index.html` — load `chatHistory.js`; scroll-to-bottom button delegates to
  `chatHistory.scrollToBottom()`
- `static/style.css` — `overflow-anchor:none` on the window's sentinels/spacer
- `tests/test_chat_history_js.py` — static-analysis tests
- `tests/test_chat_history_playwright.py` — Playwright integration tests
- `tests/test_chat_history_a11y_js.py` — accessibility contract tests
- `tests/test_chat_history_render_paging_playwright.py` — end-to-end render/paging
  regression suite against the live app
- `tests/test_chat_history_longsession_playwright.py` — automated long-session streaming
  soak (real send path, mock model)
- `tests/bench/live_app.py`, `tests/bench/scroll_driver.js`, `tests/bench/mock_llm.py` —
  real-app bootstrap, scroll-walk driver, and mock OpenAI-compatible model server the
  end-to-end suites run on

Dependency: the end-to-end paging suite requires the paginated `/api/history` endpoint
to actually be reachable. A legacy unpaginated route currently shadows it; that
route-shadowing fix is staged as a separate PR, and the suite skips (with an explicit
reason) rather than fails until it lands.

## Measured evidence (comparison matrix)

Source: `tests/bench/` harness, published artifact `tests/bench/results/bench.{json,md}`
(5 kept repeats, Chromium 148 headless; #4661's trim/reload vendored faithfully from its
commit `27f35e1c` as `tests/bench/vendor/trimChatHistory_4661.js`, provenance-guarded by
`tests/test_bench_vendor_4661.py`). Worst-case column n=5000 messages; full curve
(250/1000/2000/5000) in the artifact.

| Axis (n=5000) | Unpatched baseline | #4661 | This PR (`MessageWindow`) |
|---|---|---|---|
| Steady-state DOM nodes after load | 39,014 | 1,274 (150-msg cap holds) | 411 |
| DOM nodes at top of history | 39,088 | **39,092** — click-reload restores all; no re-trim until next message | 2,196 |
| Renderer USS at top of history (MB) | 119.8 | 122.9 | **62.5** |
| Reaching old history | scroll (all live) | 97 "show older" clicks, full restore, scroll position lost | scroll-up pages in place, window stays bounded |
| Append layout cost, 25-msg stream (ms) | 101.3 | 4.7 | 3.2 |
| Scroll smoothness (mean frame ms) | 16.7 | 16.7 | 16.7 |
| Review size (source lines changed) | — | ~142 | ~1,490 (5 files; plus ~2,830 test lines) |

The two rows that decide it: #4661's cap genuinely bounds the steady state, but the moment
a user reads old history the bound is gone — the DOM and USS return to the unpatched
values and stay there until the next message re-trims. This PR's window holds (~2.2k nodes,
half the baseline's USS) at the deepest point of a 5000-message history, which is exactly
the long-session reading pattern #4644 describes. Cost rows are honest in both directions:
#4661 matches us on append and scroll smoothness, and is a fraction of the review size.

## Relationship to upstream #4661

This change and open upstream PR #4661 (holden093, `fix/browser-memory-leak`) target the
same problem: an unbounded chat-history DOM that causes the long-session OOM (#4644). The
relationship is precise, and stated honestly:

- **Independent architecture, predating #4661 by nine days.** This branch's first commit
  ("virtual message window and scroll fixes to prevent renderer OOM") was authored
  2026-06-11 20:47 UTC; #4661 opened 2026-06-20 21:07 UTC. The `MessageWindow` design,
  bidirectional windowing, and eviction model predate #4661's existence.
- **A fuller per-node teardown.** Beyond clearing the app's per-node timer handles, this
  releases `_streamRenderer` references, disconnects the IntersectionObserver (`_sObs`), and
  releases hljs-defer observer references via `hljsDeferForgetNode`. Those uncleaned
  observers and renderers were confirmed leak sources in the fork's OOM investigation
  (`docs/fork/memory-explosion-research.md`).
- **The windowing is more complete.** #4661 is a focused top-only trim (~142 lines): a
  150-node cap, removal from the top, and a "load older" bar backed by server pagination.
  This adds bidirectional windowing so a user can scroll back up and reload evicted
  messages in place.

**Where the extra lines go, and why they earn their keep.** The two approaches differ less
in *what* they fix than in *where* they place the complexity. #4661 keeps the diff small
(~142 lines) by trimming the live DOM in place and debouncing the thinking renderer; this PR
spends its lines on a message-index model (`MessageWindow`) that only ever renders a bounded
slice of the message array. That trade is real, and it buys structural guarantees rather than
runtime bookkeeping: a windowed slice *cannot* delete a live agent thread or tool timeline —
only the rendered range is ever in the DOM, so there is nothing to mis-trim — and it *cannot*
be defeated by streaming nodes slipping past a node count, because the bound is on messages,
not nodes. A compact in-place trimmer has to re-establish those same guarantees by hand, at
runtime, which is genuinely hard: #4661's public review history shows several rounds of
change-requests for exactly these edges — trimming that reached live timeline nodes, thinking
text lost across terminal transitions, and a multi-round cap that overshot its target. Those
are honest bugs in a hard problem, and they are noted here as evidence for the design choice,
not as a mark against the author's work. They are the reason the additional structure pays for
itself.

Scope, stated honestly: this PR carries the DOM-window half. The streaming-side vectors #4661
also addresses (thinking-block O(n²), background-stream payload release, StreamRenderer
teardown) are handled in the companion `fix/dom-oom-streaming-throttle`. Two narrower items
#4661 includes are deliberately not mirrored here, for concrete reasons: its running-stream
*admission cap* is unnecessary in this codebase — our `_purgeStaleBackgroundStreams` frees only
terminal (completed/error) entries and never aborts running work, so there is no destructive
cap that would need admission control to be made safe; and its independent *document-finalize
guard* addresses a real but unrelated doc-streaming robustness gap that is tracked as its own
fix rather than bundled into an OOM change.

Trade-off, stated plainly: #4661 is smaller and lower review cost; this is larger, with an
independent architecture, a fuller teardown, and bidirectional scroll-up. A maintainer may
reasonably prefer either. This is offered on its technical merits, acknowledging #4661 as
parallel work on the same leak class. If the maintainer prefers #4661's direction, the
extended teardown and windowing here can instead be contributed on top of it.

## Related

- Companion branch `fix/dom-oom-streaming-throttle` fixes the remaining OOM vectors in
  `chat.js` (thinking-block O(n^2) `mdToHtml`, rAF throttle, StreamRenderer teardown,
  background-stream cleanup, GC yield). That one is complementary to #4661, not competing.
- Research: `docs/fork/memory-explosion-research.md`.

## Filing order

File upstream issue first. File this PR before `fix/dom-oom-streaming-throttle` (the streaming PR references this one). Close issue #65 as folded into #2.
