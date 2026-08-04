# PR Draft: fix/history-route-shadow -> odysseus-dev/odysseus:dev

**Branch:** `fix/history-route-shadow`
**Status:** Ready to file
**Base:** cut from `upstream-mirror`, 1 file, +8/-9

---

## Title

`fix(history): remove the legacy /api/history route shadowing the paginated endpoint`

---

## Summary

### Problem

**The history pagination endpoint has never run.**

`routes/session_routes.py` mounts with `prefix="/api"` and is registered *before*
`routes/history`. Its `GET /api/history/{sid}` ignores `limit`/`offset` and
returns the full history. FastAPI matches the first-registered route, so it
shadows the paginated `GET /api/history/{session_id}` in
`history_routes.get_session_history`, which is never reached.

The consequences are silent, which is why this survived:

- scroll-up pagination returns the **entire** history on every request
- `has_more_before` is never sent, so the client-side pager cannot activate
- nothing errors; the data is correct, just unbounded

A long session therefore fetches its whole history in one shot while the code
reads as though it pages.

### Fix

Remove the shadowing route. `get_session_history` already serves the no-limit
case through its own fallback, returning the **identical** `{role, content,
metadata}` shape — that is `ChatMessage.to_dict()` on both sides — so it fully
subsumes the removed handler.

The no-limit callers (`documentLibrary`, session copy/export) are unaffected;
they hit the same shape from the surviving endpoint.

### Why this is a deletion rather than a reorder

Reordering the registrations would work, but leaves two handlers for one path
and the next router-registration change reintroduces the bug. Deleting the
subsumed one removes the ambiguity.

---

## Verification

The branch carries **no test files**, and that is worth stating plainly rather
than implying coverage: the change is the removal of a route whose replacement is
already exercised by the existing history tests. The shape equivalence
(`ChatMessage.to_dict()` on both sides) was checked by reading both handlers, not
by a new assertion.

If a test is wanted before merge, the natural one asserts that exactly one route
answers `GET /api/history/{sid}` and that it accepts `limit`/`offset` — say so
and it will be added.

---

## Scope

`routes/session_routes.py`, +8/-9.
