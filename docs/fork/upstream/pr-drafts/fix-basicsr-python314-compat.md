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

There are two paths in Odysseus that can trigger `pip install realesrgan`:

1. **Cookbook Dependencies tab** (`/api/cookbook/packages/install` in `shell_routes.py`)
   — the primary user-facing install button.
2. **Serve panel** (`/api/model/serve` in `cookbook_routes.py`) — when a user pastes
   a `pip install realesrgan` command manually.

Both paths are covered.

**Shared preflight (`cookbook_helpers.py`):**

`_append_realesrgan_basicsr_preflight()` generates a self-contained Python script that:
1. Exits immediately if basicsr is already importable.
2. Exits immediately if Python < 3.10 (neither incompatibility applies).
3. Downloads the `basicsr==1.4.2` source archive from PyPI (no binary, no deps).
4. **Patch 1:** Rewrites `get_version()` in `setup.py` to use an explicit namespace dict
   instead of relying on `locals()`:
   ```python
   def get_version():
       namespace = {}
       with open(version_file, 'r') as f:
           exec(compile(f.read(), version_file, 'exec'), namespace)
       return namespace['__version__']
   ```
5. **Patch 2:** Walks all `.py` files in the extracted tree and replaces bare
   `from collections import Mapping/MutableMapping/Sequence/MutableSequence` with the
   correct `from collections.abc import ...` form.
6. Installs the patched source tree in-place.
7. The original `pip install realesrgan` then proceeds and resolves its remaining
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
- `tarfile.extractall` uses `filter="data"` on Python 3.12+ for security.
- Patch 1 only writes `setup.py` if the original pattern is still present — fails
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
- [x] I ran `python -m pytest` — 71 tests pass, 0 failures.
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
2. In the Odysseus UI, go to **Cookbook → Dependencies → Real-ESRGAN → Install**.
   The Dependencies tab install button uses `/api/cookbook/packages/install`, which
   is the path most users follow. Confirm the preflight runs and basicsr installs.
3. Confirm `import basicsr` succeeds and an ESRGAN upscale works end-to-end.

**Unit tests:**
```bash
python -m pytest tests/test_cookbook_helpers.py -k "basicsr or realesrgan" -v
```
11 tests cover: positive/negative detection, Python executable extraction, Python < 3.10
no-op scope guard, exec/locals patch content, collections.abc patch content, PowerShell
runner path, POSIX runner path, already-installed no-op (subprocess exit 0), and
`run_basicsr_preflight_async` is a coroutine.

---

## Filing Notes

- Single squashed commit as of 2026-06-15. Ready to file as-is.
- **File upstream issue first** — draft in `docs/fork/upstream/issue-drafts/fix-basicsr-python314-compat.md`.
  Add the upstream issue number to `Fixes #` above before opening the PR.
- Acknowledge PR #3741 in the PR description if it is still open at filing time; the
  body above already does this.

**Verify before filing (items not confirmed at draft time):**
- **CPython issue #118888** — cited in both the issue draft and this PR. Verify the
  number against https://github.com/python/cpython/issues before filing; if wrong,
  replace with the correct issue or cite the Python 3.13 changelog directly.
- **PR #3741 scope** — we assert it covers exec/locals only. Read the actual diff of
  PR #3741 before filing; if it already patches collections.abc, adjust the comparison.
- **collections.abc coverage in basicsr 1.4.2** — we patch Mapping, MutableMapping,
  Sequence, MutableSequence. Manually verify against the actual 1.4.2 source that no
  other removed collections ABCs (Callable, Iterable, Iterator, etc.) are imported by
  basicsr. Run: `pip download --no-binary :all: basicsr==1.4.2 -d /tmp/bsr && cd /tmp
  && tar xf /tmp/bsr/basicsr-1.4.2.tar.gz && grep -r "from collections import"
  basicsr-1.4.2/ | grep -v ".abc"` to find any misses.

## Visual / UI changes

None — no HTML, CSS, or DOM-writing JS was changed.
