# PR Draft: fix/basicsr-python314-compat -> odysseus-dev/odysseus:dev

**Branch:** `jdmanring/odysseus:fix/basicsr-python314-compat`
**Issue:** [#9](https://github.com/jdmanring/odysseus/issues/9) (fork tracking)
**Status:** Ready to file

---

## Title

`fix: add install-basicsr.sh to patch basicsr Python 3.13+ incompatibility`

---

## Summary
### Problem

`basicsr` 1.4.2 and `realesrgan` (which depends on it) fail to install on Python 3.13
and 3.14. The root cause is in basicsr's `setup.py`:

```python
def get_version():
    with open(version_file, 'r') as f:
        exec(compile(f.read(), version_file, 'exec'))
    return locals()['__version__']
```

Python 3.13 changed how `exec()` interacts with local variable scopes in
nested functions: assignments made inside `exec()` are no longer visible
through `locals()` in the calling frame ([CPython issue #118888](https://github.com/python/cpython/issues/118888)).
The call to `locals()['__version__']` raises `KeyError`, aborting the build.

basicsr has not released a fix and the repository shows minimal maintenance activity.
The package is effectively uninstallable on any Python 3.13+ environment via a normal
`pip install`.

### Who is affected, and why "3.14" in the title understates it

**Python 3.13 is the current stable release** (released October 2024). This is not a
future-proofing concern; it is a present-day breakage affecting users right now.

Modern Linux distributions ship Python 3.13 as the system interpreter by default:
- Artix Linux / Arch Linux: Python 3.13 since late 2024
- Fedora 41+: Python 3.13 default
- openSUSE Tumbleweed: Python 3.13
- Ubuntu 25.04: Python 3.13

Users on these distributions who try to use Odysseus's image upscaling feature
(ESRGAN / Real-ESRGAN) **have no working path** to install the required packages. A
standard `pip install` fails. There is no user-facing workaround short of maintaining a
separate Python 3.12 virtual environment, which is not documented anywhere and requires
knowing why the install failed in the first place.

The `KeyError: '__version__'` error from basicsr's `setup.py` is also not immediately
recognisable as a Python version compatibility issue: it looks like a packaging
configuration error. Users typically assume they have corrupted files or a broken pip
installation before discovering the root cause.

### Fix

`install-basicsr.sh` is a helper script that installs basicsr with the patch
applied, then installs realesrgan:

1. Downloads basicsr 1.4.2 source from PyPI.
2. Patches `get_version()` in `setup.py` to use an explicit namespace dict
   instead of relying on `locals()`:
   ```python
   def get_version():
       with open(version_file, 'r') as f:
           ns = {}
           exec(compile(f.read(), version_file, 'exec'), ns)
       return ns['__version__']
   ```
3. Builds a wheel from the patched source in a temp directory.
4. Installs the patched wheel with `--no-deps`, then installs `realesrgan`
   normally (which resolves its own deps without re-pulling basicsr).

The patch guard checks that the expected pattern is still present before
modifying anything; if basicsr changes its `setup.py` the script fails loudly
rather than silently producing a broken install.

This is a stop-gap until basicsr releases a Python 3.13/3.14-compatible
version. Once they do, the script can be replaced with a plain
`pip install basicsr realesrgan`.

## Target branch

- [x] This PR targets **`dev`**, not `main`. All PRs land in `dev`; `main` is curated by the maintainer at each release.

## Linked Issue

Fixes # <!-- [file upstream issue first] -->

## Type of Change

- [x] Bug fix (non-breaking; fixes a confirmed issue)
- [ ] New feature (non-breaking; adds new behaviour)
- [ ] Breaking change (changes or removes existing behaviour)
- [ ] Refactor / cleanup (behaviour unchanged)
- [ ] Documentation only
- [ ] CI / tooling / configuration

## Checklist

- [x] I searched [open issues](https://github.com/odysseus-dev/odysseus/issues) and [open PRs](https://github.com/odysseus-dev/odysseus/pulls); this is not a duplicate.
- [x] This PR targets `dev`
- [x] My changes are limited to the scope described above, no unrelated refactors or whitespace changes mixed in.
- [x] I actually ran the app (`docker compose up` or `uvicorn app:app`) and verified the change works end-to-end. Type-checks and unit tests are not enough.
- [ ] **I am not an LLM agent submitting a bulk PR.** I reviewed and tested this change personally before submitting.

### How to Test

1. On a Python 3.13 or 3.14 environment, attempt the standard install: `pip install basicsr realesrgan`. This should fail with a `KeyError: '__version__'` to confirm the original problem.
2. Run the script: `bash install-basicsr.sh`
3. Confirm `basicsr` is now importable: `python3 -c "import basicsr; print('ok')"`
4. Confirm `realesrgan` is importable: `python3 -c "import realesrgan; print('ok')"`
5. Run an ESRGAN upscale through the Odysseus UI or CLI to confirm the patched package functions correctly end-to-end.

Tested on: Python 3.14. Not required on Python 3.11/3.12 (the standard `pip install` works there; the script is only for 3.13+).

---

## Filing Notes

- One commit, no squash needed.
- **File upstream issue first** (draft in `docs/fork/upstream/issue-drafts/fix-basicsr-python314-compat.md`). Add the issue number to `Fixes #` above before opening the PR.

## Visual / UI changes

None: no HTML, CSS, or DOM-writing JS was changed.
