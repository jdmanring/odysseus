# PR Draft — fix/chat-history-dom-eviction (commit 1: route-shadowing fix)

**Branch**: `fix/chat-history-dom-eviction` (from `upstream-mirror`), commit 1 of 2.
**Related issue draft**: `docs/fork/upstream/issue-drafts/fix-history-route-shadowing.md`
**Status**: staged + verified. NOT filed. Candidate to file as its **own** small PR
(it fixes a merged-but-inert maintainer feature and is independently valuable); the
eviction graft (commit 2) depends on it.

## Title

fix(history): remove legacy `/api/history` route shadowing the paginated endpoint

## What & why

The maintainer's history pager (`45ee5a71`) is inert: a pre-existing legacy route
`GET /api/history/{sid}` in `routes/session_routes.py` (router `prefix="/api"`,
registered before `routes/history`) shadows the paginated
`GET /api/history/{session_id}` in `history_routes.get_session_history`. FastAPI
matches the first-registered route, so the backend never paginates —
`?limit=24` returns the full history, `has_more_before` is never sent, and the
frontend pager never installs. See the linked issue for full root-cause.

## Change

Remove the legacy `get_history` handler. `get_session_history` already handles the
no-`limit` case via its fallback and returns the identical `{role, content,
metadata}` shape (`== ChatMessage.to_dict()`), so it fully subsumes the route.

### Behaviour note (deliberate)

For no-`limit` callers (`documentLibrary` copy-chat, session copy/export), the
surviving `get_session_history` fallback differs from the removed handler in two
intentional ways:
- **content truncation:** messages longer than `HISTORY_DISPLAY_CHAR_LIMIT` (160 KB)
  are head+tail truncated by `_history_display_content`.
- **hidden rows skipped:** messages with `metadata.hidden` (compaction summaries)
  are omitted.

Both are desirable for those callers (a copied transcript shouldn't include internal
compaction rows; 160 KB single messages are pathological), but they are a behaviour
change and are called out here so the maintainer can accept them explicitly.

## Verification

- `tests/test_chat_history_eviction_playwright.py::test_backend_paginates_history`
  — boots the real app against a seeded DB; asserts `?limit=24` returns 24 rows +
  `total` + `has_more_before` (guards against the shadow returning).
- No-`limit` callers audited: `documentLibrary._copyChatById`, session copy/export
  read only `role`/`content`/`metadata` — all present in the fallback shape.

## Notes

- Independently valuable — revives a merged-but-dead maintainer feature.
- Prerequisite for the eviction graft (commit 2), which is gated on a working pager.
