# PR Draft: fix/basicsr-python314-compat → pewdiepie-archdaemon/odysseus:dev

**Branch:** `jdmanring/odysseus:fix/basicsr-python314-compat`
**Issue:** [#9](https://github.com/jdmanring/odysseus/issues/9) (fork tracking)
**Status:** Ready to file — file upstream issue first (draft in issue-drafts/fix-basicsr-python314-compat.md)

---

## Title

`fix(cookbook): pre-install patched basicsr 1.4.2 for Real-ESRGAN on Python 3.13+`

---

## Summary

### Problem

`basicsr` 1.4.2 (a dependency of `realesrgan`) fails to build on Python 3.13+.
realesrgan 0.3.0 ships a universal wheel and installs without building; basicsr 1.4.2
ships only a source distribution and must be compiled from source via `setup.py`.

`setup.py`'s `get_version()` reads the version file via `exec()` then calls `locals()`:

```python
def get_version():
    with open(version_file, 'r') as f:
        exec(compile(f.read(), version_file, 'exec'))
    return locals()['__version__']
```

Python 3.13 changed how `exec()` interacts with local variable scopes in nested
functions per PEP 667: assignments made inside `exec()` are no longer visible through
`locals()` in the calling frame. This raises `KeyError: '__version__'` and aborts the
build before pip can install basicsr.

The change is tracked in [CPython issue #118888](https://github.com/python/cpython/issues/118888),
which was closed as expected behavior per PEP 667 — a permanent semantic change in
Python 3.13, not a bug that will be reverted.

basicsr has not released a fix and the repository shows minimal maintenance activity.

**Impact:** Python 3.13 is the current stable release (released October 2024). Modern
Linux distributions ship it as the default interpreter (Arch/Artix since late 2024,
Fedora 41+, openSUSE Tumbleweed, Ubuntu 25.04). The Real-ESRGAN upscaler is
completely unavailable to users on any up-to-date system.

### Relationship to PR #3741

PR #3741 ("fix(cookbook): install realesrgan on Python 3.13") addresses the same
exec/locals build failure. This PR adopts the same integrated `cookbook_helpers.py`
preflight approach as #3741 and extends it to cover a second install path that
#3741 misses.

### Fix

There are two paths in Odysseus that can trigger `pip install realesrgan`:

1. **Cookbook Dependencies tab** (`/api/cookbook/packages/install` in `shell_routes.py`)
   — the primary user-facing install button. **Not covered by PR #3741.**
2. **Serve panel** (`/api/model/serve` in `cookbook_routes.py`) — when a user pastes
   a `pip install realesrgan` command manually. Covered by PR #3741.

Both paths are covered by this PR.

**Shared preflight (`cookbook_helpers.py`):**

`_append_realesrgan_basicsr_preflight()` generates a self-contained Python script that:
1. Exits immediately if Python < 3.13 (the scoping change is 3.13+ only).
2. Exits immediately if basicsr is already importable.
3. Fetches the `basicsr==1.4.2` sdist URL from the PyPI JSON API and downloads
   it with `urllib.request` — `pip download --no-binary :all:` would invoke
   `get_requires_for_build_wheel`, running setup.py and hitting the same
   `KeyError` the preflight is here to prevent.
4. Rewrites `get_version()` in `setup.py` to use an explicit namespace dict
   instead of relying on `locals()`:
   ```python
   def get_version():
       namespace = {}
       with open(version_file, 'r') as f:
           exec(compile(f.read(), version_file, 'exec'), namespace)
       return namespace['__version__']
   ```
5. Installs the patched source tree in-place.
6. The original `pip install realesrgan` then proceeds and resolves its remaining
   dependencies without re-pulling basicsr.

`run_basicsr_preflight_async()` wraps the same script for use by direct Python
callers that don't build a shell runner script.

**Wiring:**

- `cookbook_routes.py` (Serve panel): preflight injected into both POSIX (heredoc
  `<<'PY'`) and PowerShell (`@'...'@`) runner scripts before `req.cmd` is appended.
  Both paths include an inline abort: POSIX checks `ODYSSEUS_PREFLIGHT_EXIT` immediately
  after the heredoc and exits before `req.cmd` on non-zero; PowerShell checks
  `$LASTEXITCODE -ne 0` inline.
- `shell_routes.py` (Dependencies tab): `install_package()` awaits
  `run_basicsr_preflight_async()` before the normal `asyncio.create_subprocess_exec`
  install when `pip_name == "realesrgan"`.

**Other guards:**
- `tarfile.extractall` uses `filter="data"` on Python 3.12+ for security (parameter
  added in 3.12; becomes the default in 3.14).
- The setup.py patch only writes if the original pattern is still present — fails
  loudly rather than silently producing a broken install if basicsr ever releases a fix.

## Target branch

- [x] This PR targets **`dev`**, not `main`. All PRs land in `dev`; `main` is curated by the maintainer at each release.

## Linked Issue

Fixes # <!-- [file upstream issue first using issue-drafts/fix-basicsr-python314-compat.md] -->

## Type of Change

- [x] Bug fix (non-breaking — fixes a confirmed issue)
- [ ] New feature (non-breaking — adds new behaviour)
- [ ] Breaking change (changes or removes existing behaviour)
- [ ] Refactor / cleanup (behaviour unchanged)
- [ ] Documentation only
- [ ] CI / tooling / configuration

## Checklist

- [x] I searched [open issues](https://github.com/pewdiepie-archdaemon/odysseus/issues) and [open PRs](https://github.com/pewdiepie-archdaemon/odysseus/pulls) — this is not a duplicate (see PR #3741 note above).
- [x] This PR targets `dev`
- [x] My changes are limited to the scope described above — no unrelated refactors or whitespace changes mixed in.
- [x] I ran `python -m pytest` — 76 tests pass, 0 failures.
- [ ] **I am not an LLM agent submitting a bulk PR.** I reviewed and tested this change personally before submitting.

### How to Test

**Confirming the bug (Python 3.13+):**
```bash
python -m pip install basicsr==1.4.2
# → KeyError: '__version__'
```

**Testing the fix:**
1. On a Python 3.13+ environment, trigger the Real-ESRGAN Cookbook task in Odysseus.
   The preflight should print its banner, patch, and install basicsr before realesrgan
   installs cleanly.
2. Confirm basicsr is importable: `python -c "import basicsr; print('ok')"`
3. Run an ESRGAN upscale through the UI to confirm end-to-end.

**Testing the Dependencies tab path (shell_routes.py):**
1. In the Odysseus UI, go to **Cookbook → Dependencies → Real-ESRGAN → Install**.
2. Confirm the preflight runs and basicsr installs before the realesrgan install.
3. Confirm `import basicsr` succeeds and an ESRGAN upscale works end-to-end.

**Unit tests:**
```bash
python -m pytest tests/test_cookbook_helpers.py -k "basicsr or realesrgan" -v
```
17 tests cover: positive/negative detection, Python executable extraction, Python < 3.13
no-op scope guard, exec/locals patch content, PowerShell runner path, POSIX runner path
(with inline abort), already-installed no-op (subprocess exit 0),
`run_basicsr_preflight_async` is a coroutine, the namespace-dict patch eliminates the
KeyError on Python 3.13+, `install_package()` calls the preflight before pip for the
`realesrgan` package (the Dependencies tab path), preflight failure aborts the install,
urllib.request is used (not `pip download`), and `run_basicsr_preflight_async` propagates
the subprocess return code.

---

## Filing Notes

- **File upstream issue first** — draft in `docs/fork/upstream/issue-drafts/fix-basicsr-python314-compat.md`.
  Add the upstream issue number to `Fixes #` above before opening the PR.
- Acknowledge PR #3741 in the PR description if it is still open at filing time; the
  body above already does this.

**Verify before filing:**
- **CPython issue #118888** — verified: exists, describes the exec/locals scoping change,
  closed as expected behavior per PEP 667. Cite confidently.
- **PR #3741 scope** — verified: patches exec/locals in `cookbook_helpers.py` and
  `cookbook_routes.py` only; does not touch `shell_routes.py`. This PR's additional
  coverage claim is accurate.
- **basicsr 1.4.2 collections imports** — verified against the actual sdist
  (SHA256: `b89b595a87ef964cda9913b4d99380ddb6554c965577c0c10cb7b78e31301e87`): every
  `from collections import` uses only `OrderedDict` or `Counter`; no ABC names are
  imported. No collections.abc fix is needed or included.

## Visual / UI changes

None — no HTML, CSS, or DOM-writing JS was changed.
