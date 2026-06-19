# Upstream Issue Draft: fix-api-token-utcnow-deprecated

**File on:** `pewdiepie-archdaemon/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/fix-api-token-utcnow-deprecated.md`
**Branch:** `fix/api-token-utcnow-deprecated`
**Fork issue:** [#51](https://github.com/jdmanring/odysseus/issues/51)
**Type:** Bug
**Context:** Follow-up to upstream commit `790ef81b` ("fix: use aware UTC in health timestamp")

---

## Title

`fix(auth): replace deprecated datetime.utcnow() in api-token last_used_at update`

---

## Body

**Install method:** Docker / manual Python

**OS / device:** Any

**Python version:** 3.12+ (deprecation warning); will break on eventual removal

**Problem:**

`app.py` updates `ApiToken.last_used_at` using the deprecated `datetime.utcnow()`:

```python
# app.py — _touch_last_used (API token auth middleware)
_db.query(ApiToken).filter(ApiToken.id == tid).update(
    {"last_used_at": datetime.utcnow()}
)
```

`datetime.utcnow()` has been deprecated since Python 3.12. The project already has the correct abstraction in `core/database.py`:

```python
def utcnow_naive() -> datetime:
    """Return naive UTC for existing DateTime columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
```

Every other timestamp write in the codebase uses `utcnow_naive()` — all `TimestampMixin` columns and all explicit writes in `database.py`. `ApiToken.last_used_at` is a plain `DateTime` column (no timezone) that stores naive UTC, consistent with the rest of the schema. This call was the only site in the codebase still using the deprecated API directly.

Commit `790ef81b` ("fix: use aware UTC in health timestamp") fixed the same class of deprecation in the `/api/health` endpoint but missed this instance.

**Note:** `datetime.now()` at the nightly skill-audit loop (also in `app.py`) is intentional — it computes a next-run time in local wall-clock terms so the job fires at a configurable local hour (default 2 AM). That call is correct and not affected by this fix.
