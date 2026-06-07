# [UPSTREAM] realesrgan / basicsr Broken on Python 3.14

## Status
- Issue filed: Not yet filed
- PR opened: Not yet opened
- Fix in fork: `install-basicsr.sh` patches both failures; working on Python 3.14.5

## Notes
Two distinct failure modes confirmed on Python 3.14.5. The fork's patch script is the
reference implementation for any upstream fix. Upstream may prefer a version gate +
warning over a patched wheel, since they can't own a basicsr fork. Either approach is
acceptable — mention both in the issue and let the maintainer decide.

---

## Staged Issue
<!-- James: open https://github.com/pewdiepie-archdaemon/odysseus/issues/new?template=bug_report.yml and paste below -->

**Steps to Reproduce**

**Failure 1 — build-time (pip install realesrgan)**

1. Run Python 3.14 with a clean venv.
2. In the Cookbook, trigger the realesrgan install (or run `pip install realesrgan` manually).

**Failure 2 — runtime (import after patched install)**

1. After a successful install (e.g. via pre-patched wheel), launch Odysseus.
2. Open the Cookbook and check the realesrgan status.

**Expected Behaviour**

1. `pip install realesrgan` completes successfully.
2. Cookbook shows realesrgan as "Installed" and functional.

**Actual Behaviour**

**Failure 1 — build-time:**
```
KeyError: '__version__'
```
`basicsr/setup.py` uses `exec(open('basicsr/version.py').read()) + locals()['__version__']`
which fails on Python 3.14 because `exec()` no longer populates the caller's local scope.

**Failure 2 — runtime:**
```
ImportError: cannot import name 'rgb_to_grayscale' from 'torchvision.transforms.functional_tensor'
```
`basicsr/data/degradations.py` imports from `torchvision.transforms.functional_tensor`,
which was removed in recent torchvision versions (symbols moved to
`torchvision.transforms.functional`).

**Root Cause**

`basicsr` is an unmaintained dependency of `realesrgan`. It was not written for Python 3.14
and has not been updated for recent torchvision API changes.

**Confirmed Fix (applied in fork)**

1. Build-time: patch `setup.py` to pass a namespace dict to `exec()`:
   ```python
   ns = {}; exec(open('basicsr/version.py').read(), ns); version = ns['__version__']
   ```
2. Runtime: in `basicsr/data/degradations.py`, change import source:
   ```python
   # Before:
   from torchvision.transforms.functional_tensor import rgb_to_grayscale
   # After:
   from torchvision.transforms.functional import rgb_to_grayscale
   ```

**Options for Upstream**

1. Patch `basicsr` inline during the Cookbook install step (shell patch or sed).
2. Gate the install on Python version and display a clear warning to Python 3.14+ users.
3. Improve Cookbook error reporting to distinguish "package not found" from "package
   crashed on import" — currently both show as "Not Installed."

**Install Method:** Manual Python install

**OS:** Linux

**Willing to submit a fix:** Yes — I can open a PR

---

## Staged PR
<!-- James: file the issue first, get the number, fill in Fixes #NNN below, then open PR -->

### Summary

`basicsr` (required by `realesrgan`) is broken on Python 3.14 in two independent ways:
a build-time `KeyError` in `setup.py` and a runtime `ImportError` from a stale
torchvision import. Both are confirmed and patched in this fork. This PR adds either
an inline patch to the Cookbook installer or a clear Python version gate with a user-
facing error, depending on the approach the maintainer prefers.

### Target branch
- [x] This PR targets **`dev`**, not `main`.

### Linked Issue

Fixes #

### Type of Change
- [x] Bug fix (non-breaking — fixes a confirmed issue)

### Checklist
- [x] Searched open issues and open PRs — not a duplicate
- [x] Targets `dev`
- [x] Changes limited to described scope
- [ ] App run locally on Python 3.14 and realesrgan install verified *(must do before filing)*

### How to Test

1. Set up Odysseus on Python 3.14 with a clean venv.
2. Open the Cookbook and trigger the realesrgan install.
3. Confirm installation completes without `KeyError: '__version__'`.
4. Confirm Cookbook shows realesrgan as "Installed."
5. Test image upscaling via the Cookbook — confirm no `ImportError` at runtime.

### Visual / UI changes

None — Cookbook installer logic and/or error message text only. If error message text
changes, attach a screenshot of the Cookbook status panel.
