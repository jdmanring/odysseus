# [UPSTREAM] Pytest-Timeout Dependency

## Problem
The test runner calls pytest with `--timeout=60`, but `pytest-timeout` is not listed in `requirements.txt` or `pyproject.toml`. This causes warnings and potential hangs on clean installations.

## Fix
Add `pytest-timeout>=2.3.0` to the development/test requirements section.

## Status
- [ ] Identified
- [ ] PR ready for upstream `dev` branch
