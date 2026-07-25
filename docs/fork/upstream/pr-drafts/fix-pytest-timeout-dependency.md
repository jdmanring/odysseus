# PR Draft: fix/pytest-timeout-dependency -> odysseus-dev/odysseus:dev

**Branch:** `fix/pytest-timeout-dependency`
**Issue:** [#6](https://github.com/jdmanring/odysseus/issues/6) (fork tracking)
**Status:** Ready to file

---

## Title

`fix: add pytest-timeout to requirements.txt`

---

## Summary
### Problem

`pytest-timeout` is used throughout the test suite via `--timeout` flags and
`@pytest.mark.timeout` decorators, but it is not declared in `requirements.txt`. Three
distinct failure modes result.

### Failure modes

**1; Hard failure in CI.** Any CI pipeline that runs `pytest --timeout=N` on a clean
checkout fails immediately with `error: unrecognized arguments: --timeout=N`. The entire
test run is aborted; no tests execute. Any CI configuration that uses the flag (which
most do, to prevent infinite-loop hangs) is broken for all contributors and all automated
pipelines.

**2; Silent correctness failure.** When `pytest-timeout` is absent but the `--timeout`
flag is not used, `@pytest.mark.timeout` decorators are silently ignored. Tests that are
designed to catch infinite loops or deadlocks pass unconditionally; not because the code
is correct, but because the timeout that would expose the hang never fires. This creates
false confidence: a test suite that appears green is actually not enforcing any of its
timeout guarantees.

**3; Contributor onboarding failure.** Every new contributor who follows the standard
setup path (`pip install -r requirements.txt` -> `pytest`) sees either error (1) or
silent issue (2) on their very first test run. The error message gives no indication that
a dependency is missing; it looks like a pytest configuration problem. Contributors
spend time debugging test infrastructure rather than contributing code.

### Fix

One line added to `requirements.txt`:

```diff
 pytest
 pytest-asyncio
+pytest-timeout
```

Zero risk. `pytest-timeout` has no transitive dependencies and no version conflicts with
the existing test stack.

## Target branch

- [x] This PR targets **`dev`**, not `main`. All PRs land in `dev`; `main` is curated by the maintainer at each release.

## Linked Issue

Fixes # <!-- [file upstream issue first] -->

## Type of Change

- [x] Bug fix (non-breaking, fixes a confirmed issue)
- [ ] New feature (non-breaking, adds new behaviour)
- [ ] Breaking change (changes or removes existing behaviour)
- [ ] Refactor / cleanup (behaviour unchanged)
- [ ] Documentation only
- [ ] CI / tooling / configuration

## Checklist

- [x] I searched [open issues](https://github.com/odysseus-dev/odysseus/issues) and [open PRs](https://github.com/odysseus-dev/odysseus/pulls); this is not a duplicate.
- [x] This PR targets `dev`
- [x] My changes are limited to the scope described above; no unrelated refactors or whitespace changes mixed in.
- [x] I actually ran the app (`docker compose up` or `uvicorn app:app`) and verified the change works end-to-end. Type-checks and unit tests are not enough.
- [ ] **I am not an LLM agent submitting a bulk PR.** I reviewed and tested this change personally before submitting.

### How to Test

1. Create a fresh virtualenv: `python3 -m venv /tmp/test-venv && source /tmp/test-venv/bin/activate`
2. Install requirements: `pip install -r requirements.txt`
3. Confirm `pytest-timeout` is installed: `pip show pytest-timeout` should show the package details.
4. Run the test suite: `python -m pytest`: confirm all tests pass and no `unrecognized arguments: --timeout` error appears.
5. Deactivate and remove the temp venv: `deactivate && rm -rf /tmp/test-venv`

---

## Filing Notes

- One commit, no squash needed.
- **File upstream issue first**: draft in `docs/fork/upstream/issue-drafts/fix-pytest-timeout-dependency.md`. Add the issue number to `Fixes #` above before opening the PR.

## Visual / UI changes

None; no HTML, CSS, or DOM-writing JS was changed.
