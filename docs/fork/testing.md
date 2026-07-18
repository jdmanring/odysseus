# Testing Standards for the Odysseus Fork

This document defines the testing architecture and standards for the internal fork. 

## Philosophy
Testing is not a separate phase; it is an integral part of the feature delivery. Every new feature, bug fix, or infrastructure change must be accompanied by a corresponding test that validates the change and prevents regression.

## Project Structure
- **Project-level tests**: Located in `/tests`.
- **Tooling tests**: Located in `/tests/tooling`.
- **Integration tests**: Located in `/tests/integration`.

## Testing Standards

### 1. Unit Tests
- Use `unittest` or `pytest` (standardized on `unittest` for now).
- Each test should target a single behavior or edge case.
- Tests must be deterministic and isolated from other tests.

### 2. Tooling Validation
For binaries and external dependencies (handled by `BinManager`):
- **Existence**: Test that the binary is found or correctly installed.
- **Functionality**: Test that the binary can be executed (e.g., via `--version` or equivalent).
- **Graceful Failure**: Test how the system handles missing or corrupt binaries.

### 3. Coupling Requirements
Every Pull Request (PR) must include:
- The implementation code.
- The corresponding test case.
- Updated documentation (if applicable).

## How to Run Tests
To run all tests in the project:
```bash
python3 -m unittest discover tests
```

To run specific tooling tests:
```bash
python3 -m unittest tests/tooling
```

## Suite Gates Before a Merge (hard rule)

A merge to `develop` is gated on the FULL suite's **own exit code** — never on a
pipeline's. Piping swallows the test runner's status: `pytest ... | tail -3`
exits with `tail`'s 0, and a merge once landed on a 4-failure suite exactly this
way (2026-07-17). The safe shape:

```bash
venv/bin/python -m pytest -q > /path/to/suite.log 2>&1; echo "pytest-exit:$?"
```

Merge only on `pytest-exit:0`; on any other value, read the log, fix forward,
re-run. Reading "N passed" off a truncated tail is not a gate. The same applies
to any chained command: a `&&` chain that begins with a formatter or `tail`
gates on the wrong program.

## Convergence Guards

Two drift classes have bitten this fork and each now has a mechanical guard —
extend the pattern rather than re-deriving it:

- `tests/test_bench_vendor_snapshot_drift.py`: a vendored benchmark snapshot
  must byte-match its live source (re-vendor + re-run the bench on drift).
- `tests/test_staged_branch_convergence.py`: the staged upstream branch's
  converged files must match the maintained versions, whole-line comments
  excluded (the staged branch legitimately differs only in scrubbed
  fork-issue references). Re-converge on drift; see issue #131.
