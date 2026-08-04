# PR Draft: fix/test-temp-db-leak -> odysseus-dev/odysseus:dev

**Branch:** `fix/test-temp-db-leak`
**Issue:** #174 (fork tracking, `docs/fork/issues/INDEX.md`)
**Upstream issue draft:** `docs/fork/upstream/issue-drafts/fix-test-temp-file-leak.md`
**Status:** Ready to file
**Base:** cut from `upstream-mirror`, two commits

---

## Title

`fix(tests): remove the temp databases and directories the suite leaves behind`

---

## Summary

### Problem

The suite creates file-backed sqlite databases and temp directories and removes
neither.

**Per full-suite run** (`tests/`, excluding `tests/bench`), which is the
reproducible figure:

| resource | leaked per run | source |
|---|---|---|
| `tmp*.db` | 29 | 20 modules + `tests/helpers/sqlite_db.py` |
| `tmp*/` directories | 23 | 8 module-level `mkdtemp`, 3 in-test |
| `odysseus_*` data dirs | 8 | module-level `mkdtemp` with a prefix |

Nothing removes any of them, so the count grows without bound across runs.

These are per-run and reproducible with the command below.

### Why it is worth fixing

Where `/tmp` is a RAM-backed tmpfs, these are resident in memory. Here `/tmp`
reached 100% full with 114 MB free of 16 GB, and Playwright's Chromium started
crashing: 10 tests failed with `Page.goto: Page crashed` or `ERROR at setup`.

Those failures read as a code regression. Two of them are
`test_merge_touched_module_imports` and `test_no_module_breakage_signatures`,
whose entire job is catching a bad merge resolution, so the false signal lands
exactly where a maintainer is most likely to trust it. All 10 pass in isolation
once space is freed.

### Where it comes from

`tests/helpers/sqlite_db.py` arrived in #2930 as the first low-risk slice of the
#2523 migration, and that PR deliberately scoped cleanup out:

> It does not patch modules, bind `SessionLocal`, manage cleanup, or own global
> state.

Reasonable for a proving slice. The migration was not continued, so the helper
and the 20 modules that hand-roll the same block all carry `delete=False` with
no counterpart. This PR finishes that migration rather than second-guessing the
original call.

---

## What changed

The mechanism is chosen by **where the allocation happens**, which is the whole
design decision here:

**Inside a test or fixture -> pytest's `tmp_path`.** It prunes itself, keeps the
last few runs for debugging, and needs no machinery from us. The suite already
uses it correctly in `tests/test_inside_base_dir_nonstring.py`.

This covers `tests/test_workspace_confine.py`, which produced most of the
directory count: its `ws` fixture plus five separate in-test
`outside = tempfile.mkdtemp()` calls. The five collapse into one `outside`
fixture, so the file gets shorter as well as correct.

**At module import time -> `tests/helpers/temp_cleanup.py`.** A small registry
swept at interpreter exit. These allocations run before any fixture exists and
are assigned to module globals shared by every test in the file, so
`tmp_path_factory` genuinely cannot see them. That constraint is the only reason
the module exists; it is not a general-purpose temp API.

`tests/helpers/sqlite_db.py` delegates to the same registry instead of carrying
its own, so there is one sweep to audit rather than two. Its public surface
(`make_temp_sqlite`) is unchanged, so the 10 existing callers need no edits.

**Also removed:** a dead `ws = tempfile.mkdtemp()` in `tests/test_edit_file.py`.
The result was never read, so it leaked a directory per run for nothing.

**Two guard tests.** This defect reappeared once per new test file that copied
the idiom, and nothing else in the suite would notice. One fails on a new
hand-rolled `NamedTemporaryFile(suffix=".db", delete=False)`, the other on a new
module-level `mkdtemp`. In-test `mkdtemp` is deliberately allowed: that is
`tmp_path`'s territory and the guard should not push people off it.

---

## Verification

Full suite, `tests/` excluding `tests/bench`, same machine, same invocation:

| | result | `.db` leaked | dirs leaked | `odysseus_*` leaked |
|---|---|---|---|---|
| `upstream-mirror` | 4787 passed, 1 skipped | **29** | **23** | **8** |
| this branch | 4795 passed, 1 skipped | **0** | **0** | **0** |

The +8 is exactly the guard tests this PR adds; no existing test changed state.

Reproduce:

```
before=$(ls -1U /tmp | grep -c '^tmp.*\.db$')
python -m pytest tests/ -q --ignore=tests/bench
after=$(ls -1U /tmp | grep -c '^tmp.*\.db$')
echo "leaked: $((after-before))"
```

---

## Scope note

Production code is not touched and does not need to be. All 12
`delete=False`/`mkstemp`/`mkdtemp` sites in `src/`, `core/`, `routes/` and
`mcp_servers/` already clean up in a `try/finally`;
`routes/document_routes.py` uses a `_to_unlink` list with a `finally` sweep. A
user running the application never triggers this, which is the likeliest reason
it went unnoticed since June.

**Precedent:** #1018 (`fix(stt): always remove the temp audio file, even when
transcription fails`), merged, is the same defect shape in the STT path.

---

## Unrelated pre-existing failure seen while measuring

`test_list_sessions_excludes_other_users_sessions` passes alone and fails when
run beside its sibling modules, on `upstream-mirror` with and without this
change. Not caused by this PR.

Root cause: `routes/session_routes.py` defines a module-global `APIRouter`, so
every `setup_session_routes()` call in the suite appends another `/api/sessions`
route to it, and the test's `next(...)` picks an earlier test's endpoint bound to
a different mock. Taking the last-registered match fixes it.

That fix is a separate PR rather than folded in here, because it touches a
different file for a different reason. Reproduced on a clean `upstream-mirror`
(twice, with `/tmp` empty, so it is not the exhaustion described above): 1 failed
/ 69 passed without it, 70 passed with it.
