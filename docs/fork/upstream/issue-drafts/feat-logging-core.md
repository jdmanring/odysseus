# Upstream Issue Draft: feat-logging-core

**File on:** `odysseus-dev/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/feat-logging-core.md`
**Branch:** `feat/logging-core`
**Type:** Enhancement
**References:** Addresses the PII and audit logging findings from #3803

---

## Title

`[Logging] Structured logging with request correlation, PII redaction, and auth audit trail`

---

## Body

**Area:** Logging / Observability / Security

**Problem / Motivation:**
Odysseus uses stdlib `logging` throughout (~1038 calls across 138 files) but lacks production-grade logging capabilities. The hardening audit in #3803 identified two logging problems this PR addresses:

- "PII (emails, usernames, message bodies) logged at INFO level in several paths"
- "No audit trail for sensitive operations (auth events, vault unlock, admin wipes)"

Additionally, there is no request correlation (no way to trace a specific request across log lines), no structured output format for aggregation tools, and no per-subsystem debug control without changing code.

**Proposed Solution:**
Replace stdlib `logging` with [structlog](https://www.structlog.org/) while preserving full backward compatibility — existing `logging.getLogger()` calls continue to work via structlog's stdlib integration.

New capabilities:

**Request correlation:** `AccessLoggingMiddleware` generates a UUID4 `request_id` per request, binds it to `contextvars`, and returns it as `X-Request-ID`. All log calls within a request automatically include the request ID.

**PII redaction:** Key-name-based sensitive data redaction (Sentry-style denylist) — matches field names like `email`, `password`, `token`, `content`. Never scans string values, so legitimate string content isn't accidentally censored.

**Auth audit trail:** Login success/failure (with reason), signup, logout, password change, admin user create/delete, and every settings change (actor + key + old value → new value) are logged as structured audit events.

**Structured output:** JSON file output (`data/logs/odysseus.log`) + human-readable console output. Configurable via `ODYSSEUS_LOG_FORMAT` and `ODYSSEUS_LOG_FILE`.

**Per-subsystem debug:** `ODYSSEUS_DEBUG_SUBSYSTEMS=chroma,embeddings` enables DEBUG level on specific loggers without global debug noise.

**Alternatives Considered:**
Full migration of all 1038 `logging` calls to structlog: high risk, large diff, hard to review. The structlog stdlib integration makes a drop-in replacement possible — new code uses `structlog.get_logger()`, existing code works without changes.

**Note:** This PR does not address all items in #3803. The unversioned migrations, non-atomic writes, missing owner scoping, and DB session handling items are separate and out of scope here.
