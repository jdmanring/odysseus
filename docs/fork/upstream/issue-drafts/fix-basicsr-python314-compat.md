# Upstream Issue Draft: fix-basicsr-python314-compat

**File on:** `odysseus-dev/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/fix-basicsr-python314-compat.md`
**Branch:** `fix/basicsr-python314-compat`
**Type:** Bug

---

## Title

`[Cookbook] basicsr fails to build on Python 3.13+: Real-ESRGAN upscaler broken`

---

## Body

**Install method:** manual Python

**OS / device:** Any (Python 3.13 or later)

**Steps to Reproduce:**
1. Set up a Python 3.13+ environment.
2. Trigger the Real-ESRGAN Cookbook task; Odysseus runs `pip install realesrgan`, which pulls in `basicsr==1.4.2` as a build-from-source dependency (no wheel on PyPI).

**Expected:** basicsr builds and installs successfully and the upscaler runs.

**Actual:** Installation fails during the basicsr build phase with `KeyError: '__version__'`:
```
KeyError: '__version__'
  File "setup.py", line N, in get_version
    return locals()['__version__']
```

**Root cause:**

`basicsr/setup.py`'s `get_version()` function uses `exec()` to evaluate the version file, then reads the result via `locals()['__version__']`. Python 3.13 changed how `exec()` interacts with local variable scopes in nested functions per PEP 667: assignments made inside `exec()` are no longer visible through `locals()` in the calling frame. This raises `KeyError: '__version__'`, aborting the build before pip can install basicsr.

The relevant CPython change is tracked in [issue #118888](https://github.com/python/cpython/issues/118888). The issue was closed as expected behavior per PEP 667; this is a permanent change in Python 3.13's semantics, not a bug that will be reverted.

basicsr has not released a fix and the repository shows minimal maintenance activity. realesrgan 0.3.0 ships a universal wheel (`py3-none-any.whl`) and installs without building, but its basicsr dependency does not.

**Who is affected:**

Python 3.13 is the current stable release (released October 2024). Modern Linux distributions ship Python 3.13 as the system interpreter:
- Artix Linux / Arch Linux: Python 3.13 since late 2024
- Fedora 41+: Python 3.13 default
- openSUSE Tumbleweed: Python 3.13
- Ubuntu 25.04: Python 3.13

Users on any of these distributions who try to use Odysseus's Real-ESRGAN upscaler have no working install path. There is no user-facing workaround short of maintaining a separate Python 3.12 virtual environment.

**Additional context:** PR #3741 also addresses this exec/locals issue, but only wires the fix into the Serve panel (`cookbook_routes.py`). The Cookbook Dependencies tab (`shell_routes.py`) is not covered by #3741 and is the path most users follow.
