# [UPSTREAM] pytest-timeout Not Declared as a Dependency

## Status
- Issue filed: Not yet filed
- PR opened: Not yet opened
- Fix in fork: Not needed (fork doesn't invoke --timeout in its own CI)

## Notes
Trivial one-liner. No app changes, no screenshot. Good first PR.

---

## Staged Issue
<!-- James: open https://github.com/pewdiepie-archdaemon/odysseus/issues/new?template=bug_report.yml and paste below -->

**Steps to Reproduce**

1. Clone the repo on a clean system (fresh venv, no pre-installed packages).
2. `pip install -r requirements.txt`
3. `python -m pytest --timeout=60`

**Expected Behaviour**

Tests run with the timeout active; hanging tests are killed at 60 seconds.

**Actual Behaviour**

```
PytestUnknownMarkWarning: Unknown pytest.mark.timeout - is this a custom mark?
```
On some runners `--timeout` is silently ignored and tests with blocking I/O hang
indefinitely, stalling CI.

**Root Cause**

`pytest-timeout` is used implicitly (via `--timeout=60` in the test runner command)
but is not declared in `requirements.txt`, `pyproject.toml`, or any requirements file.
A fresh environment will not have it.

**Proposed Fix**

Add `pytest-timeout>=2.3.0` to the test/dev dependencies.

**Install Method:** Manual Python install

**OS:** Linux

**Willing to submit a fix:** Yes — I can open a PR

---

## Staged PR
<!-- James: file the issue first, get the number, fill in Fixes #NNN below, then open PR -->

### Summary

`pytest-timeout` is called via `--timeout=60` but never declared as a dependency.
Clean environments drop timeout silently. One-line fix: add `pytest-timeout>=2.3.0`
to the test dependencies.

### Target branch
- [x] This PR targets **`dev`**, not `main`.

### Linked Issue

Fixes #

### Type of Change
- [x] Bug fix (non-breaking — fixes a confirmed issue)

### Checklist
- [x] Searched open issues and open PRs — not a duplicate
- [x] Targets `dev`
- [x] Changes limited to described scope
- [ ] App run locally and verified *(must do before filing)*

### How to Test

1. Fresh venv: `python -m venv /tmp/t && source /tmp/t/bin/activate`
2. `pip install -r requirements.txt`
3. `pip show pytest-timeout` — confirm it is now installed
4. `python -m pytest --timeout=60` — confirm no `PytestUnknownMarkWarning`

### Visual / UI changes

None — dependency declaration only.
