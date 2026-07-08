# Decision Record — Chat-History Rendering Architecture

**Status:** Decided. Not open for re-litigation. Reopen only if upstream ships DOM eviction of their own (see "When to revisit").
**Scope:** How the fork renders long chat histories, and what we contribute upstream.
**Regression guard:** `tests/test_chat_history_render_paging_playwright.py` (on `develop`).

---

## The question

Upstream shipped its own history pager (`_installHistoryPager`, direct commit `45ee5a71`). The fork
has its own, older, larger history stack (`static/js/chatHistory.js`, `MessageWindow`). Do we keep
ours, or drop it for theirs?

**The only test that matters: is ours better?** It is. So we keep ours. This document records why,
so it is not asked a third time.

## The comparison (read the code, not the vibes)

| | Upstream `_installHistoryPager` (`sessions.js`, ~60 lines) | Fork `MessageWindow` (`chatHistory.js`, ~1000 lines) |
|---|---|---|
| Defers full-history render on open | ✅ | ✅ |
| Pages **older** from server on scroll-up | ✅ (`loadOlder`, prepend) | ✅ (`_fetchOlderFromServer` → `_all`) |
| Pages **newer** back in | ❌ | ✅ (`_loadNewer`) |
| **Evicts DOM nodes** as you scroll | ❌ — prepends forever | ✅ (`_maybePrune`, `_evictLive`, `_pruneTop`, `_pruneBottom`) |
| Bounded live node count on a long history | ❌ | ✅ (top/bottom IntersectionObserver sentinels) |
| Scroll-anchor on prepend (no viewport jump) | ✅ (`scrollHeight` delta) | ✅ |

**The decisive gap:** upstream's pager only *defers* the OOM. It never removes a node, so scrolling
up through a long conversation grows the DOM without bound — the exact failure `MessageWindow` was
built to prevent. Ours holds memory flat regardless of history length. Upstream has no
`chatHistory.js` at all.

**Verdict: ours completely supersedes upstream's recent history work.** Keep `MessageWindow` on
`develop` as a deliberate fork enhancement. This is not carried debt — it is a better implementation
we maintain on purpose.

## What we learned from theirs

Their prepend scroll-anchor (capture `box.scrollHeight` before insert, add the delta back to
`scrollTop`) is clean. `MessageWindow` already does the equivalent; keep it that way.

## What goes upstream (we stage; the human files — hard rule)

We do **not** ask upstream to undo their pager. Two cooperative contributions, both on
`fix/chat-history-dom-eviction` (cut from `upstream-mirror`):

1. **Route-shadowing fix (#125).** A legacy `GET /api/history/{sid}` on the sessions router shadows
   the paginated endpoint, so upstream's *own* pager never receives `has_more_before` and is inert.
   This fix makes their feature actually run — a pure gift, no contest.
   Draft: `docs/fork/upstream/pr-drafts/fix-history-route-shadowing.md`.
2. **Bounded-DOM eviction (#2).** Eviction offered as an enhancement layered on their pager. Since
   upstream lacks the `MessageWindow` substrate, this branch is the pragmatic small-patch form of our
   idea, ported onto their code — we hand them the improvement our design proved out.
   Draft: `docs/fork/upstream/pr-drafts/fix-chat-history-dom-eviction.md`.

Per the issue-lifecycle rule, #125 and #2 stay open until those upstream PRs are filed.

## How we don't regress

- **`tests/test_chat_history_render_paging_playwright.py`** (on `develop`) is the guard. It boots a
  real server + Chromium and asserts: backend paginates (`?limit` honoured, `has_more_before` sent);
  `selectSession` actually renders bubbles; scroll-up reaches the oldest message via server paging;
  the DOM never holds the entire history. It would have caught — and now prevents — the
  `markdownModule is not defined` regression (`_mapHistoryMessages` threw on every session load,
  history rendered empty, error swallowed by `selectSession`'s catch).
- The static source-grep + mock-DOM tests **do not** exercise the real render path — that blind spot
  is exactly how the `markdownModule` break shipped. Any change to `chatHistory.js`, `sessions.js`
  `_mapHistoryMessages`/`_installHistoryPager`, or the `/api/history` route **must** keep the
  Playwright guard green; do not rely on the greps alone.

## When to revisit

Only if upstream ships genuine DOM **eviction** (not just paging) of their own. At that point
re-run this comparison against their new code. Until then: course is set — keep ours, ship them the
fix + the eviction concept.
