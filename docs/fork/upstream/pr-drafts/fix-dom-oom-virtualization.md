> **⚠️ REFRAMED / SUPERSEDED (2026-07-07).** This draft describes the abandoned
> 916-line `MessageWindow` *port* strategy. It was reframed after finding the
> maintainer shipped their own history pager (commit `45ee5a71`), which owns the
> history render + scroll path this branch tried to replace. The current approach
> is a small **eviction graft** on top of the maintainer's pager — see
> `docs/fork/upstream/pr-drafts/fix-history-route-shadowing.md` (prerequisite route
> fix) and the eviction graft on branch `fix/chat-history-dom-eviction`. Also
> **retracted:** the "adapted from #4661 teardown" claim below (recon §7/§8). The
> resolved, exactly-true framing is in plan Part 1.2 (2026-07-18): no influence claim
> in either direction — the teardown was authored ~5h after #4661 opened (timeline
> proves nothing), the only resemblance is clearing the app's own
> `_waveInterval`/`_elapsedTicker` fields (an idiom any removal path must use), and
> #4661's mechanism was never used. Do not file this draft as-is.

# PR Draft — fix/dom-oom-virtualization

**Branch**: `fix/dom-oom-virtualization` (from `upstream-mirror`)
**Issue**: jdmanring/odysseus#2
**Upstream issue**: file before filing PR
**Status**: Not yet submittable; the draft body needs a full rewrite at file time (plan
Part 5). Provenance framing corrected 2026-07-18 (plan Part 1.2, primary-source verified):
**independent architecture, timeline-proven** — authored from 2026-06-11 (author dates),
nine days before #4661 opened. The `_evictLive` teardown makes **no influence claim in
either direction**: authored ~5h after #4661 opened (timeline proves nothing), its only
overlap with #4661 is clearing this app's own timer handles (an idiom forced on any
implementation removing these nodes), and #4661's actual mechanism was never used. #4661
is acknowledged as parallel work on the same leak class — nothing more is claimed.

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

## Teardown pattern provenance

The per-node cleanup in `_evictLive()` clears this app's own `_waveInterval`/`_elapsedTicker` handles before removing an element -- an idiom forced on any implementation that removes these nodes, and the only lines overlapping #4661's `_trimChatHistoryDOM()`. That function itself is not used: it destroys chatHistory.js control elements (sentinel, spacer, histSep). No influence claim is made in either direction (plan Part 1.2).

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

## Relationship to upstream #4661

This change and open upstream PR #4661 (holden093, `fix/browser-memory-leak`) target the
same problem: an unbounded chat-history DOM that causes the long-session OOM (#4644). The
relationship is precise, and stated honestly:

- **Architecture is independent and predates #4661 by nine days.** This branch's first
  commit ("virtual message window and scroll fixes to prevent renderer OOM") was AUTHORED
  2026-06-11 20:47 UTC (author date; an earlier record cited the rebase commit-date of
  2026-06-20 01:42 UTC); #4661 opened 2026-06-20 21:07 UTC. The `MessageWindow` design,
  bidirectional windowing, and eviction model predate #4661's existence.
- **The per-node teardown: no influence claim, either direction.** It was authored ~5h
  after #4661 opened, so the timeline proves nothing; its only overlap with #4661's
  `_trimChatHistoryDOM()` is clearing this app's own `_waveInterval`/`_elapsedTicker`
  handles, which any removal path must clear. `_trimChatHistoryDOM()` itself is not used
  (it destroys this implementation's control elements: sentinel, spacer, histSep).
- **The teardown goes beyond anything in #4661.** In addition to those interval clears, this
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
