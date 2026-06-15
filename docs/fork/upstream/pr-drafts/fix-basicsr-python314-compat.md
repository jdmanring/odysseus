# PR Draft: fix/basicsr-python314-compat → pewdiepie-archdaemon/odysseus:dev

**Branch:** `jdmanring/odysseus:fix/basicsr-python314-compat`
**Issue:** [#9](https://github.com/jdmanring/odysseus/issues/9) (fork tracking)
**Status:** Ready to file — file upstream issue first (draft in issue-drafts/fix-basicsr-python314-compat.md)

---

## Title

`fix(cookbook): pre-install patched basicsr 1.4.2 for Real-ESRGAN on Python 3.10+`

---

## Summary

### Problem

`basicsr` 1.4.2 (a dependency of `realesrgan`) fails to install or import on Python 3.10+
due to two separate incompatibilities that have never been patched upstream.

**Incompatibility 1 — exec/locals scoping (Python 3.13+):**

`setup.py`'s `get_version()` reads the version file via `exec()` then calls `locals()`:

```python
def get_version():
    with open(version_file, 'r') as f:
        exec(compile(f.read(), version_file, 'exec'))
    return locals()['__version__']
```

Python 3.13 changed how `exec()` interacts with local variable scopes in nested
functions: assignments made inside `exec()` are no longer visible through `locals()` in
the calling frame ([CPython issue #118888](https://github.com/python/cpython/issues/118888)).
This raises `KeyError: '__version__'` and aborts the pip install before basicsr builds.

**Incompatibility 2 — collections.abc removals (Python 3.10+):**

Several basicsr source files import abstract base classes directly from `collections`:

```python
from collections import Mapping
from collections import MutableMapping
```

These were moved to `collections.abc` in Python 3.3 and the old names were removed in
Python 3.10. This causes an `ImportError` at import time on any Python 3.10–3.12
environment (the exec/locals bug masks this on 3.13+, but it is present there too).

**Impact:** basicsr is broken for installation on Python 3.13+ and broken at import on
Python 3.10+. Python 3.10 is five years old and Python 3.13 is the current stable
release. Every modern Linux distribution ships Python 3.13 as the default interpreter.
The Real-ESRGAN upscaler is completely unavailable to users on any up-to-date system.

### Relationship to PR #3741

PR #3741 ("fix(cookbook): install realesrgan on Python 3.13") addresses incompatibility 1
(exec/locals) only. It does not patch the collections.abc import breakage that affects
Python 3.10–3.12. This PR adopts the same integrated `cookbook_helpers.py` preflight
approach as #3741 and extends it to cover both incompatibilities.

### Fix

Adds `_append_realesrgan_basicsr_preflight()` to `cookbook_helpers.py`. This function
is called automatically from `cookbook_routes.py` before any `pip install realesrgan`
command runs — no manual step required.

The preflight:
1. Detects whether basicsr is already installed; exits immediately if so.
2. Downloads the `basicsr==1.4.2` source archive from PyPI (no binary, no deps).
3. **Patch 1:** Rewrites `get_version()` in `setup.py` to use an explicit namespace dict
   instead of relying on `locals()`:
   ```python
   def get_version():
       namespace = {}
       with open(version_file, 'r') as f:
           exec(compile(f.read(), version_file, 'exec'), namespace)
       return namespace['__version__']
   ```
4. **Patch 2:** Walks all `.py` files in the extracted tree and replaces bare
   `from collections import Mapping/MutableMapping/Sequence/MutableSequence` with the
   correct `from collections.abc import ...` form.
5. Installs the patched source tree in-place.
6. The original `pip install realesrgan` command then runs as normal and resolves
   its remaining dependencies without re-pulling basicsr.

Guards:
- The preflight is a no-op when basicsr is already installed (`import basicsr` succeeds).
- The preflight is a no-op on Python < 3.10 (neither incompatibility applies).
- `tarfile.extractall` uses `filter="data"` on Python 3.12+ for security; omitted on
  earlier versions where the parameter does not exist.
- Patch 1 only writes `setup.py` if the original pattern is still present, so the
  script fails loudly rather than silently producing a broken install if basicsr ever
  releases a fix.

Both POSIX (heredoc) and PowerShell (`@'...'@`) runner paths are covered.

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
- [x] I ran `python -m pytest` — 69 tests pass, 0 failures.
- [ ] **I am not an LLM agent submitting a bulk PR.** I reviewed and tested this change personally before submitting.

### How to Test

**Testing incompatibility 1 (Python 3.13+):**
1. On a Python 3.13+ environment, confirm the raw install fails:
   `python -m pip install basicsr==1.4.2` → `KeyError: '__version__'`
2. Trigger the Real-ESRGAN Cookbook task in Odysseus. The preflight should run, patch,
   and install basicsr before realesrgan installs cleanly.
3. Confirm basicsr is importable: `python -c "import basicsr; print('ok')"`
4. Run an ESRGAN upscale through the UI to confirm end-to-end.

**Testing incompatibility 2 (Python 3.10–3.12):**
1. On a Python 3.10, 3.11, or 3.12 environment, confirm the import fails after a
   normal install: `pip install basicsr==1.4.2 && python -c "import basicsr"` →
   `ImportError: cannot import name 'Mapping' from 'collections'`
2. Trigger the Real-ESRGAN Cookbook task. Preflight should patch and install cleanly.
3. Confirm `import basicsr` succeeds.

**Unit tests:**
```bash
python -m pytest tests/test_cookbook_helpers.py -k "basicsr or realesrgan" -v
```
9 tests cover: positive/negative detection, Python executable extraction, Python < 3.10
no-op scope guard, exec/locals patch content, collections.abc patch content, PowerShell
runner path, POSIX runner path, and already-installed no-op.

---

## Filing Notes

- One commit, no squash needed.
- **File upstream issue first** — draft in `docs/fork/upstream/issue-drafts/fix-basicsr-python314-compat.md`.
  Add the upstream issue number to `Fixes #` above before opening the PR.
- Acknowledge PR #3741 in the PR description if it is still open at filing time; the
  body above already does this.

## Visual / UI changes

None — no HTML, CSS, or DOM-writing JS was changed.
