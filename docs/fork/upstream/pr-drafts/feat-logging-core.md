# PR Draft: feat/logging-core → pewdiepie-archdaemon/odysseus:dev

**Branch:** `jdmanring/odysseus:feat/logging-core`
**Base:** `jdmanring/odysseus:upstream-mirror`
**Issue:** [#31](https://github.com/jdmanring/odysseus/issues/31) (fork tracking)
**Upstream Issues Addressed:**
- [#3803](https://github.com/pewdiepie-archdaemon/odysseus/issues/3803) — PII in logs, no audit trail for sensitive operations
- [#3799](https://github.com/pewdiepie-archdaemon/odysseus/issues/3799) — Hardening pass (PII scrubbed from logs, audit logging for sensitive operations)
**Follow-up PR:** `feat/logging-timing` (performance timing instrumentation)
**Status:** Ready to file

---

## Title

`feat(logging): structured logging with request correlation, redaction, and JSON output`

---

## Description

### Problem

Odysseus uses stdlib `logging` throughout (~1038 calls across 138 files) but lacks production-grade logging capabilities. The upstream hardening audit (#3803) explicitly identified:
- "PII (emails, usernames, message bodies) logged at INFO level in several paths"
- "No audit trail for sensitive operations (auth events, vault unlock, admin wipes)"

Additionally, there is no request correlation, no structured output, and no per-subsystem debug control.

### Solution

Replace stdlib `logging` with [structlog](https://www.structlog.org/) while preserving full backward compatibility — existing `logging.getLogger()` calls continue to work via structlog's stdlib integration. New code uses `structlog.get_logger()` for bound context.

#### New Files

| File | Purpose |
|------|---------|
| `src/logging_config.py` | Processor pipeline: contextvars binding, sensitive data redaction, JSON file output + text console output, per-subsystem debug control via `ODYSSEUS_DEBUG_SUBSYSTEMS` |
| `src/log_context.py` | `contextvars`-based request correlation (request_id, session_key, user_id) — bind once in middleware, available in every log call |
| `src/log_redaction.py` | Key-name-based sensitive data redaction (Sentry-style denylist) — matches exact key names, never scans string values |
| `src/log_timing.py` | Performance timing context manager for critical-path operations |

#### Access Logging Middleware

`AccessLoggingMiddleware` in `app.py`:
- Generates a UUID4 `request_id` per request
- Binds it to contextvars (automatically propagated through async calls)
- Logs method, path, status code, duration at INFO/WARNING/ERROR level
- Returns `X-Request-ID` response header for client-side tracing

#### Auth Event Logging (addresses upstream #3803)

`routes/auth_routes.py`:
- Login success/failure (with reason: invalid_password, invalid_totp)
- Signup, logout, password change
- Admin user create/delete

#### Settings Audit Trail

`routes/auth_routes.py`:
- Every `POST /api/auth/settings` logs the actor, the key changed, and old → new values

#### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `ODYSSEUS_DEBUG` | `0` | Enable DEBUG level on all loggers |
| `ODYSSEUS_DEBUG_SUBSYSTEMS` | (none) | Comma-separated list of loggers to enable DEBUG for |
| `ODYSSEUS_LOG_FORMAT` | `text` | Console format: `text` or `json` |
| `ODYSSEUS_LOG_FILE` | `data/logs/odysseus.log` | Log file path |

#### Backward Compatibility

- All existing `logging.getLogger()` calls continue to work via structlog's stdlib integration
- No mass migration — only new code uses `structlog.get_logger()`
- `ODYSSEUS_DEBUG=1` behavior preserved

### Files Changed

**New files (4):**
- `src/logging_config.py`
- `src/log_context.py`
- `src/log_redaction.py`
- `src/log_timing.py`

**New dependencies (1):**
- `requirements.txt` — added `structlog`

**Modified files (5):**
- `app.py` — `AccessLoggingMiddleware`, structlog setup
- `routes/auth_routes.py` — auth event + settings audit logging
- `src/constants.py` — logging constants, typo fix (`odysseous.log` → `odysseus.log`)

**Test files (4):**
- `tests/test_log_redaction.py` — 21 tests for key-name redaction
- `tests/test_log_context.py` — 12 tests for request correlation
- `tests/test_logging_config.py` — 14 tests for setup, debug mode, JSON output
- `tests/test_logging_integration.py` — 7 integration tests (subprocess-based, end-to-end)

### Testing

- [x] 64 tests pass (59 unit + 7 integration)
- [x] App startup verified: logging initializes, produces structured JSON output
- [ ] Manual: start server with `ODYSSEUS_DEBUG=1`, verify DEBUG output
- [ ] Manual: make HTTP request, verify `X-Request-ID` header

---

## Filing Notes

This PR is built from `upstream-mirror` and contains only logging infrastructure changes. No fork-specific files. The PR should target `dev`.
