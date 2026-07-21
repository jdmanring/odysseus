# Upstream Issue Draft: fix-pytest-timeout-dependency

**File on:** `odysseus-dev/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/fix-pytest-timeout-dependency.md`
**Branch:** `fix/pytest-timeout-dependency`
**Type:** Bug

---

## Title

`pytest-timeout missing from requirements.txt — CI fails on clean environments with "unrecognized arguments: --timeout"`

---

## Body

**Install method:** manual Python

**OS / device:** Any

**Steps to Reproduce:**
1. Create a fresh virtual environment.
2. Install requirements: `pip install -r requirements.txt`
3. Run the test suite: `python -m pytest`

**Expected:** Tests run with all timeout markers enforced as declared in the test files.

**Actual:** Two failure modes depending on how `pytest` is invoked:
- If invoked with `--timeout=N` (as CI scripts commonly do): fails immediately with `error: unrecognized arguments: --timeout=N`
- If invoked without that flag: `@pytest.mark.timeout` decorators are silently ignored — tests that should time out run forever

**Logs / Error Output:**
```
error: unrecognized arguments: --timeout=60
```

**Additional context:** `pytest-timeout` is used throughout the test suite via both `--timeout` CLI flags and `@pytest.mark.timeout` decorators, but is not declared as a dependency in `requirements.txt`. The existing test dependency entries are `pytest` and `pytest-asyncio` — `pytest-timeout` should appear alongside them. This breaks CI on any clean environment and makes contributor setup unreliable.
