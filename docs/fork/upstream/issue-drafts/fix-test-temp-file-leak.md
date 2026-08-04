# Upstream Issue Draft: fix-test-temp-file-leak

**File on:** `odysseus-dev/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/fix-test-temp-file-leak.md`
**Branch:** `fix/test-temp-db-leak`
**Type:** Bug / Test infrastructure

---

## Title

`[Tests] The suite never removes its temp databases or directories`

---

## Body

**Area:** Tests

**Problem:**

The test suite creates file-backed sqlite databases and temp directories and
removes neither. They accumulate in `/tmp` for the life of the machine.

**Per full-suite run** (`tests/`, excluding `tests/bench`), which is the
reproducible figure:

| resource | leaked per run | source |
|---|---|---|
| `tmp*.db` | 29 | 20 test modules + `tests/helpers/sqlite_db.py` |
| `tmp*/` directories | 23 | 8 module-level `mkdtemp`, 3 in-test |
| `odysseus_*` data dirs | 8 | module-level `mkdtemp` with a prefix |

Nothing removes any of them, so the count grows without bound across runs.

Running just the 20 affected database modules leaves 22 files behind per run.

**Reproduction:**

Run the suite against a **private `TMPDIR`** and count what is left in it. A
before/after delta on the shared `/tmp` is not reliable: on a busy machine other
processes create and remove entries during the run, and this measurement was in
fact contaminated that way before being redone in isolation.

```
T=$(mktemp -d)
TMPDIR="$T" python -m pytest tests/ -q --ignore=tests/bench
ls -1U "$T" | grep -c '^tmp.*\.db$'          # temp databases
ls -1U "$T" | grep '^tmp' | grep -vc '\.db$'  # temp directories
ls -1U "$T" | grep '^odysseus' | grep -vc '^odysseus-tmux'  # data dirs
rm -rf "$T"
```

Two entries always survive and are **not** leaks: `pytest-of-james/` is pytest's
own `tmp_path` factory, which prunes to the last few runs by design, and
`odysseus-tmux/` is created by production code for tmux sessions, so it is
excluded above rather than counted.

The data-dir prefixes are inconsistent in the suite -- three sites use
`odysseus_` and seven use `odysseus-` -- so match on `odysseus` and subtract the
one production directory. Matching only the underscore reports 2 instead of 8.

Same for directories with `grep '^tmp' | grep -v '\.db$'`.

**Why this is worth fixing rather than tolerating:**

On a machine where `/tmp` is a RAM-backed tmpfs (the default on many systemd
distributions, and the case here at 16 GB), these are resident in memory. `/tmp`
reached 100% full with 114 MB free, and Playwright's Chromium began crashing:

```
E  playwright._impl._errors.Error: Page.goto: Page crashed
E  ERROR at setup of test_core_ui_present
```

**10 tests failed that way, and they look exactly like a code regression.** Two
of them are `test_merge_touched_module_imports` and
`test_no_module_breakage_signatures`, the tests whose job is to catch a bad merge
resolution. All 10 pass in isolation once the space is freed, so the failure is
environmental, but nothing in the output says so.

The suite is also self-reinforcing here: a crashed Chromium leaks its own
shared-memory file, which reduces available memory, which crashes the next one.

**Where it comes from:**

`tests/helpers/sqlite_db.py` was added in #2930 as the first low-risk slice of
the #2523 migration. That PR deliberately scoped cleanup out, and says so:

> It does not patch modules, bind `SessionLocal`, manage cleanup, or own global
> state.

That was a reasonable call for a proving slice. The migration was never
finished, so the helper and the 20 modules that hand-roll the same block all
carry `delete=False` with no counterpart. This issue is about completing it, not
about the original decision.

**Note on scope:** production code is not affected. All 12
`delete=False`/`mkstemp`/`mkdtemp` sites in `src/`, `core/`, `routes/` and
`mcp_servers/` clean up in a `try/finally`, and `routes/document_routes.py` uses
a `_to_unlink` list with a `finally` sweep. A user running the application never
triggers this. That is very likely why it went unnoticed: it only shows up under
repeated test runs.

**Proposed fix:**

Pick the mechanism by where the allocation happens:

- **Inside a test or fixture** -> pytest's `tmp_path`. It cleans itself up,
  keeps the last few runs for debugging, and is already used correctly elsewhere
  in the suite (`tests/test_inside_base_dir_nonstring.py`).
- **At module import time** -> a small registry swept at interpreter exit. These
  allocations happen before any fixture exists and are assigned to module
  globals shared by every test in the file, so `tmp_path_factory` cannot see
  them.

Plus two guard tests, because this reappeared once per new test file that copied
the idiom.

**Precedent:** #1018 (`fix(stt): always remove the temp audio file, even when
transcription fails`) fixed the same defect shape in the STT path and was merged.

**Willing to submit a PR:** yes, branch is ready.
