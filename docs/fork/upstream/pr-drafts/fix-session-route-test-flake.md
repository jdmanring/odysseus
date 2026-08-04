# PR Draft: fix/session-route-test-flake -> odysseus-dev/odysseus:dev

**Branch:** `fix/session-route-test-flake`
**Issue:** #175 (fork tracking, `docs/fork/issues/INDEX.md`)
**Status:** Ready to file
**Base:** cut from `upstream-mirror`, one commit (`94a4f84a`)

---

## Title

`test(sessions): take the just-registered route, not the first one`

---

## Summary

### Problem

`routes/session_routes.py` defines its `APIRouter` at module scope. Every
`setup_session_routes()` call appends another `/api/sessions` route to that same
object, and the router is never reset between tests.

Two tests pull their endpoint out of it with `next(...)`:

```python
endpoint = next(r.endpoint for r in router.routes
                if getattr(r, "path", "") == "/api/sessions"
                and "GET" in getattr(r, "methods", set()))
```

`next()` returns the **first** match, which is whichever test registered first in
the current process. That endpoint is closed over an earlier test's
`session_manager` mock, so `user_sessions` comes back empty and the ownership
assertion fails.

The tests pass when the file runs alone, because then only one route exists.
They fail whenever a sibling module has already called `setup_session_routes()`.

### Reproduction

On a clean checkout of `dev`, run the file beside other session/route modules:

```
$ python -m pytest tests/test_session_list_owner_scope.py \
      tests/test_session_actions_cleanup.py tests/test_task_chain_owner_scope.py \
      tests/test_archived_sessions_model_filter.py ... -p no:randomly
FAILED tests/test_session_list_owner_scope.py::test_list_sessions_excludes_other_users_sessions
1 failed, 69 passed
```

Reproduced twice on this machine. Alone: `2 passed`.

### Fix

Take the last-registered matching route, which is the one this test's own
`setup_session_routes()` call just appended:

```python
endpoint = [r.endpoint for r in router.routes
            if getattr(r, "path", "") == "/api/sessions"
            and "GET" in getattr(r, "methods", set())][-1]
```

Applied to both affected tests, with a comment explaining the accumulation so
the next person to copy the pattern does not reintroduce it.

### Why not reset the router instead

Clearing the module-global router between tests would be the deeper fix, and it
is tempting. It also changes behaviour for every test that touches
`setup_session_routes()`, in a suite where several modules import it at module
scope in an order pytest chooses. That is a much larger blast radius than the
defect justifies, and it is a change to production module structure made for the
benefit of tests.

This PR makes the two tests correct against the router as it actually behaves.
If upstream would rather make the router per-call or resettable, that is a
reasonable design change and this fix does not block it.

---

## Verification

| | result |
|---|---|
| the 20-module set that exposed it, without the fix | 1 failed, 69 passed |
| same set, with the fix | **70 passed** |
| `-k session` | **197 passed** |
| the file alone, before and after | 2 passed |

`/tmp` was empty for these runs, so this is not the resource exhaustion
described in the companion temp-file PR.

---

## Scope

One file, two call sites, twelve lines. No production code changes.
