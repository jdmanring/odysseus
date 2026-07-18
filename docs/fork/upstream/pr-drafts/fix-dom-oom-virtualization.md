> **⚠️ NOT FILE-READY.** The maintainer's own history pager (commit `45ee5a71`) owns
> the history render + scroll path; the alternative offering is the eviction graft on
> `fix/chat-history-dom-eviction` (with the route fix in
> `docs/fork/upstream/pr-drafts/fix-history-route-shadowing.md`). This draft's body
> needs a full rewrite at file time (plan Part 5). Provenance: plan Part 1.2 is the
> only framing to use.

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

## Test plan

- `tests/test_chat_history_js.py`: 109 static-analysis tests
- `tests/test_chat_history_playwright.py`: 11 parametrized Playwright integration test
  functions (require a running server)
- Manual: run a long agent session (80+ exchanges) and confirm DOM child count stays bounded via `document.getElementById('chat-history').children.length` in the browser console
- Manual: confirm the eviction notice appears after enough exchanges and the text is correct
- Manual: confirm `scrollTop` does not jump when eviction fires
- Manual: confirm older messages reload correctly on session switch after eviction

## Files changed

- `static/js/chatHistory.js` — new file; full `MessageWindow` implementation
- `static/js/sessions.js` — wire in `chatHistory.reset()` and `chatHistory.load()`
- `static/js/chat.js` — delegate scroll-to-bottom to `chatHistory.scrollToBottom()`
- `static/index.html` — load `chatHistory.js` before `sessions.js`
- `static/style.css` — `overflow-anchor:none`, `will-change` cleanup
- `tests/test_chat_history_js.py` — static-analysis tests
- `tests/test_chat_history_playwright.py` — Playwright integration tests

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
| Review size (lines) | — | ~145 | ~873 |

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
- **The windowing is more complete.** #4661 is a focused top-only trim (~145 lines): a
  150-node cap, removal from the top, and a "load older" bar backed by server pagination.
  This adds bidirectional windowing so a user can scroll back up and reload evicted
  messages in place.

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
