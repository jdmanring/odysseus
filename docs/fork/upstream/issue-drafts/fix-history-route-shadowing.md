# Upstream Issue Draft: fix-history-route-shadowing

**Related PR draft:** `docs/fork/upstream/pr-drafts/fix-history-route-shadowing.md`
**Branch:** `fix/chat-history-dom-eviction` (commit 1 of 2; from `upstream-mirror`)
**Type:** bug (upstream-candidate)
**Status:** staged, verified end-to-end. NOT yet filed.

## Title

fix(history): legacy `/api/history/{sid}` route shadows the paginated endpoint — history pagination never runs

## Summary

The history pager added in maintainer commit `45ee5a71` ("Polish mobile UI and
editor workflows", 2026-06-27) — frontend `_installHistoryPager` in
`static/js/sessions.js` plus the `limit`/`offset`/`has_more_before` branch in
`routes/history/history_routes.py::get_session_history` — **never activates**. A
pre-existing legacy route shadows the paginated endpoint, so the backend returns
the full history on every request and `has_more_before` is never sent.

## Root cause (verified)

- `routes/session_routes.py` mounts its router with `prefix="/api"` (registered in
  `app.py` **before** `routes/history`). It defines `GET /history/{sid}` →
  effective path `/api/history/{sid}` — a legacy handler that ignores `limit`/
  `offset` and returns the entire history.
- `routes/history/history_routes.py` defines the paginated `GET /api/history/{session_id}`
  (`get_session_history`) — the **second** registration of the same path pattern.
- FastAPI dispatches to the first-registered matching route, so the legacy route
  wins. `GET /api/history/{id}?limit=24` returns **all** messages with no `total`
  and no `has_more_before`.
- The legacy route predates the pager (present since the `e5c99a5e` base), so
  `45ee5a71` introduced the collision by adding the paginated route without
  removing the pre-existing one.

## Impact

- The history pager silently renders the **entire** conversation into the DOM on
  session open and on scroll-up — the exact unbounded-DOM behaviour the pager was
  built to avoid. On long histories this is a real perf/memory regression on the
  very sessions pagination was meant to protect (notably mobile).

## Reproduction

1. Open a session with more messages than one page (`> HISTORY_PAGE_LIMIT_DESKTOP`).
2. `GET /api/history/{id}?limit=24` → observe the response contains the full
   history, no `total`, no `has_more_before`.
3. In the UI, the scroll-up pager never installs (`has_more_before` is falsy).

## Fix

Remove the legacy `get_history` handler in `routes/session_routes.py`.
`get_session_history` already serves the no-`limit` case via its fallback with the
**identical** `{role, content, metadata}` shape (`== ChatMessage.to_dict()`), so it
fully subsumes the removed route. No-limit callers (`documentLibrary` copy-chat,
session copy/export) are unaffected in shape.

**Behaviour note (deliberate, must be stated in the PR):** for no-`limit` callers,
`get_session_history`'s fallback additionally (a) truncates message `content` over
`HISTORY_DISPLAY_CHAR_LIMIT` (160 KB) via `_history_display_content`, and (b) skips
messages whose metadata is `hidden` (e.g. compaction summaries). Both are almost
certainly desirable for the copy/export callers (hidden compaction rows shouldn't
appear in a copied transcript; 160 KB single messages are rare), but the PR must
call this out so it is a decision, not an accident.

## Verification

`tests/test_chat_history_eviction_playwright.py::test_backend_paginates_history`
asserts `?limit=24` now returns exactly 24 rows plus `total` and `has_more_before`
— a regression guard against the shadow returning.
