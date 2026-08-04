# PR Draft: fix/cookbook-hf-gguf-repo-nameerror -> odysseus-dev/odysseus:dev

**Branch:** `fix/cookbook-hf-gguf-repo-nameerror`
**Status:** Ready to file
**Base:** cut from `upstream-mirror`, 2 files, +157/-1

---

## Title

`fix(cookbook): NameError in the hf_gguf_files error path; guard defined names across routes/`

---

## Summary

### Problem

Commit `fbdec22d` rewrote the `hf_gguf_files` exception handler to log the
failure, and typed `repo` where the variable is `repo_id`.

So **the graceful-degradation path itself raises `NameError`**. `GET
/api/cookbook/hf-gguf-files` returns 500 precisely when the Hugging Face API call
fails — the one situation the handler was added to survive. The happy path is
unaffected, which is why it was not noticed: the bug only executes when something
else has already gone wrong.

One character. The fix is `repo` -> `repo_id`.

### The more useful half

A typo in an error path is invisible to tests that only exercise the success
path, and no amount of care prevents the next one. So this branch generalises the
existing `symtable` defined-names guard from `chat_routes.py` to **every module
in `routes/`**:

- renamed to `tests/test_routes_defined_names.py`
- parametrized per module, so a failure names the offending file
- implicit module globals (`__file__` and friends) allowed

It walks each module's symbol table and flags any name that is read but never
bound — catching exactly this class of defect statically, including in branches
that never run under test.

**Red-verified on the pre-fix file**: the guard fails against the original
`repo` typo, so it is demonstrably capable of catching what it claims to catch.

---

## Verification

**60 passed, 2 skipped**, measured 2026-08-03 — that is the guard running across
every module in `routes/`, so the coverage claim is the test count itself.

---

## Scope

`routes/cookbook_routes.py` (1 line) and the generalized guard (+156).
