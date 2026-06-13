# PR Draft: fix/basicsr-python314-compat → pewdiepie-archdaemon/odysseus:dev

**Branch:** `jdmanring/odysseus:fix/basicsr-python314-compat`
**Issue:** [#9](https://github.com/jdmanring/odysseus/issues/9) (fork tracking)
**Status:** Ready to file

---

## Title

`fix: add install-basicsr.sh to patch Python 3.14 incompatibilities`

---

## Description

### Problem

`basicsr` 1.4.2 and `realesrgan` (which depends on it) fail to install on
Python 3.13 and 3.14. The root cause is in basicsr's `setup.py`:

```python
def get_version():
    with open(version_file, 'r') as f:
        exec(compile(f.read(), version_file, 'exec'))
    return locals()['__version__']
```

Python 3.13 changed how `exec()` interacts with local variable scopes in
nested functions: assignments made inside `exec()` are no longer visible
through `locals()` in the calling frame. The call to `locals()['__version__']`
raises `KeyError`, aborting the build.

basicsr has not released a fix. The package is effectively uninstallable on any
Python 3.13+ environment via a normal `pip install`.

### Fix

`install-basicsr.sh` — a helper script that installs basicsr with the patch
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

### Testing

Verified on Python 3.14 — `basicsr` and `realesrgan` install cleanly and
ESRGAN upscaling functions correctly after running `install-basicsr.sh`.

---

## Filing Notes (James)

- One commit, no squash needed.
- File issue on `pewdiepie-archdaemon/odysseus` first; add its number here
  before opening the PR.
