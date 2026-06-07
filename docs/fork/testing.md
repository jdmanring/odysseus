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
