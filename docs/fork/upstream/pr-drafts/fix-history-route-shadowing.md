# PR Draft: fix/chat-history-dom-eviction (commit 1: route-shadowing fix)

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
matches the first-registered route, so the backend never paginates:
`?limit=24` returns the full history, `has_more_before` is never sent, and the
frontend pager never installs. See the linked issue for full root-cause.

## Change

Remove the legacy `get_history` handler. `get_session_history` already handles the
no-`limit` case via its fallback and returns the identical `{role, content,
metadata}` shape (`== ChatMessage.to_dict()`), so it fully subsumes the route.

### Behaviour note (deliberate: all four no-`limit` callers audited)

The four no-`limit` callers of `/api/history/{id}` (`documentLibrary._copyChatById`,
`documentLibrary` chat-preview, `sessions.js` "Copy Chat", and `sessions.js`
archived-session peek) all read only `role` and `content`. Switching them from the
removed legacy handler (raw `msg.to_dict()`) to `get_session_history`'s fallback
(via `_history_display_content`) changes the `content` payload in three ways, **all
of which are improvements or no-ops for these callers**:
- **multimodal media stripped:** list/multimodal content returns its text parts with
  image/audio blocks dropped (or `"[N media attachment(s) omitted]"`). The legacy
  route returned the raw list *including inline base64 image bytes*, e.g. "Copy Chat"
  did `JSON.stringify(content)` and would have dumped base64 into the clipboard. The
  fallback is strictly better here.
- **large-content truncation:** string content over `HISTORY_DISPLAY_CHAR_LIMIT`
  (160 KB) is head+tail truncated; the copy/preview callers already truncate further
  (600 chars for preview), so this is a no-op in practice.
- **hidden rows skipped:** `metadata.hidden` messages (compaction summaries) are
  omitted (desirable; a copied/previewed transcript shouldn't include internal rows).

No caller depends on untruncated content, raw media bytes, or hidden rows. Called out
so the maintainer accepts the change explicitly rather than by accident.

## Verification

- `tests/test_chat_history_eviction_playwright.py::test_backend_paginates_history`:
  boots the real app against a seeded DB; asserts `?limit=24` returns 24 rows +
  `total` + `has_more_before` (guards against the shadow returning).
- No-`limit` callers audited: `documentLibrary._copyChatById`, session copy/export
  read only `role`/`content`/`metadata`, all present in the fallback shape.

## Notes

- Independently valuable: revives a merged-but-dead maintainer feature.
- Prerequisite for the eviction graft (commit 2), which is gated on a working pager.
