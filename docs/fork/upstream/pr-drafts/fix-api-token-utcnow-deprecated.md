# PR Draft: fix/api-token-utcnow-deprecated → pewdiepie-archdaemon/odysseus:dev

**Branch:** `jdmanring/odysseus:fix/api-token-utcnow-deprecated`
**Fork issue:** [#51](https://github.com/jdmanring/odysseus/issues/51) (open)
**Status:** Single clean commit. File upstream issue first, fill in `Fixes #___`, then open PR.
**Context:** Follow-up to `790ef81b` ("fix: use aware UTC in health timestamp")

---

## Upstream PR title

`fix(auth): replace deprecated datetime.utcnow() in api-token last_used_at update`

---

## Summary

### Problem

`app.py` updates `ApiToken.last_used_at` with `datetime.utcnow()`, which is
deprecated since Python 3.12 and targeted for eventual removal:

```python
# _touch_last_used — fire-and-forget token activity update
_db.query(ApiToken).filter(ApiToken.id == tid).update(
    {"last_used_at": datetime.utcnow()}
)
```

The project already has the correct abstraction: `utcnow_naive()` in
`core/database.py`, which returns `datetime.now(timezone.utc).replace(tzinfo=None)`
— naive UTC suitable for the `DateTime` columns used throughout the schema. Every
other timestamp write in the codebase uses it. This was the only remaining site
using the deprecated direct call.

Commit `790ef81b` fixed the same deprecation in the health endpoint but did not
catch this instance.

### Fix

Import `utcnow_naive` and use it:

```python
# Before
from core.database import SessionLocal, ApiToken

{"last_used_at": datetime.utcnow()}

# After
from core.database import SessionLocal, ApiToken, utcnow_naive

{"last_used_at": utcnow_naive()}
```

No behavior change: both return a naive UTC datetime. The fix eliminates the
deprecation warning and aligns this call with the established project pattern.

### Scope

One file changed: `app.py` (+1 / -1 import, +1 / -1 call site). Two lines total.

---

## How to Test

1. Start Odysseus with auth enabled and at least one API token configured.
2. Make a request using the API token (bearer token in `Authorization` header).
3. Check that `ApiToken.last_used_at` is updated in the database.
4. Verify no `DeprecationWarning: datetime.utcnow()` appears in server logs under Python 3.12+.

---

## Filing Notes

- File the upstream issue first using `docs/fork/upstream/issue-drafts/fix-api-token-utcnow-deprecated.md`.
- Fill the upstream issue number into `Fixes #___` in the commit message before opening the PR:
  ```
  git checkout fix/api-token-utcnow-deprecated
  git commit --amend  # replace Fixes #51 with the upstream issue number
  git push --force-with-lease origin fix/api-token-utcnow-deprecated
  ```
- PR targets `pewdiepie-archdaemon/odysseus:dev`.
- Reference `790ef81b` (the commit that missed this site) in the PR description.
