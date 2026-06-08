# PR Draft: fix/pytest-timeout-dependency → pewdiepie-archdaemon/odysseus:dev

**Branch:** `jdmanring/odysseus:fix/pytest-timeout-dependency`
**Issue:** [#6](https://github.com/jdmanring/odysseus/issues/6) (fork tracking)
**Status:** Ready to file

---

## Title

`fix: add pytest-timeout to requirements.txt`

---

## Description

### Problem

`pytest-timeout` is used by the test suite (via `--timeout` flags and
`@pytest.mark.timeout` decorators) but is not declared in `requirements.txt`.
A fresh install runs tests without it, causing `pytest` to silently ignore all
timeout markers and any invocation with `--timeout` to fail with:

```
error: unrecognized arguments: --timeout=...
```

This breaks CI on clean environments and makes contributor setup unreliable.

### Fix

Add `pytest-timeout` to `requirements.txt` alongside the existing `pytest` and
`pytest-asyncio` entries.

```diff
 pytest
 pytest-asyncio
+pytest-timeout
```

### Testing

`pip install -r requirements.txt` in a clean virtualenv now installs
`pytest-timeout`. All existing tests pass.

---

## Filing Notes (James)

- One commit, no squash needed.
- File issue on `pewdiepie-archdaemon/odysseus` first; add its number here
  before opening the PR.
