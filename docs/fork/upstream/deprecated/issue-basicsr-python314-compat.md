# Upstream Issue Draft: fix-basicsr-python314-compat

**File on:** `odysseus-dev/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/fix-basicsr-python314-compat.md`
**Branch:** `fix/basicsr-python314-compat`
**Type:** Bug

---

## Title

`[Cookbook] basicsr / realesrgan fail to install on Python 3.13+ — ESRGAN upscaler completely broken`

---

## Body

**Install method:** manual Python

**OS / device:** Any (Python 3.13 or 3.14 environment)

**Steps to Reproduce:**
1. Set up a Python 3.13 or 3.14 environment.
2. Attempt to install basicsr: `pip install basicsr`

**Expected:** basicsr installs successfully.

**Actual:** Installation fails during the build phase with `KeyError: '__version__'`. The ESRGAN upscaler feature in Odysseus is entirely unavailable on Python 3.13+ environments.

**Logs / Error Output:**
```
KeyError: '__version__'
  File "setup.py", line N, in get_version
    return locals()['__version__']
```

**Additional context:** The root cause is in basicsr's `setup.py`. The `get_version()` function uses `exec()` to evaluate the version file, then reads the result via `locals()['__version__']`. Python 3.13 changed how `exec()` interacts with local variable scopes in nested functions: assignments made inside `exec()` are no longer visible through `locals()` in the calling frame. basicsr upstream has not released a fix and the package is uninstallable on any Python 3.13+ environment via `pip install`.

`realesrgan` depends on basicsr and fails for the same reason.

Tested on Python 3.14. Python 3.11 and 3.12 are unaffected — the standard `pip install basicsr realesrgan` works there.
