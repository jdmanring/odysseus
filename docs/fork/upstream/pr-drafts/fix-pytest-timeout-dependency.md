# PR Draft: fix/pytest-timeout-dependency → pewdiepie-archdaemon/odysseus:dev

**Branch:** `jdmanring/odysseus:fix/pytest-timeout-dependency`
**Issue:** [#6](https://github.com/jdmanring/odysseus/issues/6) (fork tracking)
**Status:** Ready to file

---

## Title

`fix: add pytest-timeout to requirements.txt`

---

## Summary
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

## Target branch

- [x] This PR targets **`dev`**, not `main`. All PRs land in `dev`; `main` is curated by the maintainer at each release.

## Linked Issue

Fixes # <!-- [file upstream issue first] -->

## Type of Change

- [x] Bug fix (non-breaking — fixes a confirmed issue)
- [ ] New feature (non-breaking — adds new behaviour)
- [ ] Breaking change (changes or removes existing behaviour)
- [ ] Refactor / cleanup (behaviour unchanged)
- [ ] Documentation only
- [ ] CI / tooling / configuration

## Checklist

- [x] I searched [open issues](https://github.com/pewdiepie-archdaemon/odysseus/issues) and [open PRs](https://github.com/pewdiepie-archdaemon/odysseus/pulls) — this is not a duplicate.
- [x] This PR targets `dev`
- [x] My changes are limited to the scope described above — no unrelated refactors or whitespace changes mixed in.
- [x] I actually ran the app (`docker compose up` or `uvicorn app:app`) and verified the change works end-to-end. Type-checks and unit tests are not enough.

### How to Test

1. Create a fresh virtualenv: `python3 -m venv /tmp/test-venv && source /tmp/test-venv/bin/activate`
2. Install requirements: `pip install -r requirements.txt`
3. Confirm `pytest-timeout` is installed: `pip show pytest-timeout` should show the package details.
4. Run the test suite: `python -m pytest` — confirm all tests pass and no `unrecognized arguments: --timeout` error appears.
5. Deactivate and remove the temp venv: `deactivate && rm -rf /tmp/test-venv`

---

## Filing Notes (James)

- One commit, no squash needed.
- File issue on `pewdiepie-archdaemon/odysseus` first; add its number here
  before opening the PR.

## Visual / UI changes

None — no HTML, CSS, or DOM-writing JS was changed.
