# Upstream Issue Draft: fix-basicsr-python314-compat

**File on:** `pewdiepie-archdaemon/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/fix-basicsr-python314-compat.md`
**Branch:** `fix/basicsr-python314-compat`
**Type:** Bug

---

## Title

`[Cookbook] basicsr / realesrgan fail to install on Python 3.10+ — ESRGAN upscaler broken`

---

## Body

**Install method:** manual Python

**OS / device:** Any (Python 3.10 or later)

**Steps to Reproduce:**
1. Set up a Python 3.10+ environment.
2. Trigger the Real-ESRGAN Cookbook task — Odysseus runs `pip install realesrgan`, which pulls in `basicsr==1.4.2`.

**Expected:** basicsr installs successfully and the upscaler runs.

**Actual:** Installation fails with one of two errors depending on Python version:

*Python 3.13+* — fails during the build phase with `KeyError: '__version__'`:
```
KeyError: '__version__'
  File "setup.py", line N, in get_version
    return locals()['__version__']
```

*Python 3.10–3.12* — fails at import time with `ImportError`:
```
ImportError: cannot import name 'Mapping' from 'collections'
```

**Root causes:**

1. **exec/locals scoping (Python 3.13+):** `basicsr/setup.py`'s `get_version()` function uses `exec()` to evaluate the version file, then reads the result via `locals()['__version__']`. Python 3.13 changed how `exec()` interacts with local variable scopes in nested functions: assignments made inside `exec()` are no longer visible through `locals()` in the calling frame ([CPython issue #118888](https://github.com/python/cpython/issues/118888)). This raises `KeyError: '__version__'`, aborting the build.

2. **collections.abc removals (Python 3.10+):** Several basicsr source files import `Mapping`, `MutableMapping`, `Sequence`, and `MutableSequence` directly from `collections`. These were deprecated in Python 3.3 and removed in Python 3.10 — they must be imported from `collections.abc`. This breaks basicsr at import time on any Python 3.10+ environment.

basicsr has not released a fix and the repository shows minimal maintenance activity. The package is effectively uninstallable or unusable on any Python 3.10+ environment.

**Who is affected:**

Python 3.10 is now five years old. Python 3.13 is the current stable release (released October 2024). Modern Linux distributions ship Python 3.13 as the system interpreter:
- Artix Linux / Arch Linux — Python 3.13 since late 2024
- Fedora 41+ — Python 3.13 default
- openSUSE Tumbleweed — Python 3.13
- Ubuntu 25.04 — Python 3.13

Users on any modern distribution who try to use Odysseus's image upscaling feature have no working path to install the required packages. There is no user-facing workaround short of maintaining a separate Python 3.9 virtual environment.

**Additional context:** PR #3741 addresses the exec/locals issue only. This issue tracks the full scope of both incompatibilities.
