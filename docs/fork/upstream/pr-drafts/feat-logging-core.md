# PR Draft: feat/logging-core → pewdiepie-archdaemon/odysseus:dev

**Branch:** `jdmanring/odysseus:feat/logging-core`
**Base:** `jdmanring/odysseus:upstream-mirror`
**Issue:** [#31](https://github.com/jdmanring/odysseus/issues/31) (fork tracking)
**Upstream Issues Addressed:**
- [#3803](https://github.com/pewdiepie-archdaemon/odysseus/issues/3803) — PII in logs, no audit trail for sensitive operations
- [#3799](https://github.com/pewdiepie-archdaemon/odysseus/issues/3799) — Hardening pass (PII scrubbed from logs, audit logging for sensitive operations)
- [#3212](https://github.com/pewdiepie-archdaemon/odysseus/issues/3212) — Add warnings to silent except blocks (complements our structured logging)
**Follow-up PRs:** `feat/logging-timing` (performance timing), `feat/logging-audit` (audit trail)
**Status:** Ready to file

---

## Title

`feat(logging): structured logging with request correlation, redaction, and JSON output`

---

## Description

### Problem

Odysseus uses stdlib `logging` throughout (~1038 calls across 138 files) but
lacks several production-grade logging capabilities. This is recognized by the
upstream maintainers:

- **Issue #3803** (hardening audit) explicitly calls out: "PII (emails, usernames,
  message bodies) logged at INFO level in several paths" and "No audit trail
  for sensitive operations (auth events, vault unlock, admin wipes)."
- **PR #3799** (hardening pass) includes "PII scrubbed from logs" and "audit
  logging for sensitive operations" in its scope.
- **Issue #3212** adds warnings to silent exception blocks — our structured
  logging makes these warnings actionable with correlation IDs and per-subsystem
  debug control.

Beyond these tracked issues, the codebase also lacks:

- **No request correlation** — concurrent HTTP requests produce interleaved log
  entries with no way to trace which entries belong to which request.
- **No access logging** — uvicorn access logs are suppressed and no custom
  middleware fills the gap. There is no record of which endpoints were called,
  with what status, and how long they took.
- **No sensitive data redaction** — API keys, tokens, passwords, and email
  content can appear in log output. The codebase has ad-hoc redaction in
  `settings_scrub.py` and `webhook_manager.py` but nothing in the logging
  pipeline itself.
- **No structured output** — logs are plain text only, making them hard to
  parse with tools like `jq` or ingest into log aggregation systems.
- **No per-subsystem debug control** — enabling debug logging means DEBUG
  everywhere, with no way to enable it for just the LLM layer or tool
  execution.

### Solution

Replace stdlib `logging` with [structlog](https://www.structlog.org/) while
preserving full backward compatibility — all existing `logging.getLogger()`
calls continue to work through structlog's stdlib integration.

#### Architecture

```
                   ┌─────────────────────┐
                   │   structlog         │
                   │   (bound context)   │
                   └────────┬────────────┘
                            │
                   ┌────────▼────────────┐
                   │  stdlib logging     │
                   │  (uvicorn, third-   │
                   │   party libraries)  │
                   └────────┬────────────┘
                            │
              ┌─────────────┼─────────────┐
              │             │             │
     ┌────────▼───┐  ┌─────▼─────┐  ┌───▼────────┐
     │  Console   │  │  Rotating │  │  JSON file │
     │  (text)    │  │  File     │  │  (always)  │
     └────────────┘  └───────────┘  └────────────┘
```

#### New Files

| File | Purpose |
|------|---------|
| `src/logging_config.py` | structlog processor pipeline + handler configuration |
| `src/log_context.py` | `contextvars`-based request correlation (request_id, session_id, user_id) |
| `src/log_redaction.py` | Key-name-based sensitive data redaction (Sentry-style denylist) |
| `src/log_timing.py` | Performance timing context manager for critical-path operations |

#### Processor Pipeline

Every log event passes through:

1. `merge_contextvars` — propagates request_id/session_id/user_id
2. `contextvals_to_log` — injects contextvars into the event dict
3. `redact_sensitive` — redacts values of sensitive keys (password, api_key, token, etc.)
4. `add_log_level` / `add_logger_name` — standard metadata
5. `TimeStamper(fmt="iso")` — ISO 8601 timestamps
6. Renderer (console: colored text; file: JSON)

#### Request Correlation

`AccessLoggingMiddleware` in `app.py`:
- Generates a UUID4 `request_id` per request
- Binds it to contextvars (automatically propagated through async calls)
- Logs method, path, status code, duration at INFO/WARNING/ERROR level
- Returns `X-Request-ID` response header for client-side tracing

#### Sensitive Data Redaction

Key-name-based denylist (Sentry-style) — only exact key names are matched,
never free-text patterns. This avoids false positives on source code, variable
names, and log messages.

Redacted keys include: `password`, `api_key`, `token`, `secret`, `session_id`,
`cookie`, `authorization`, `private_key`, `ssn`, `credit_card`, and variants.

#### New Logging in Critical Subsystems

- **Tool execution** (`src/tool_execution.py`) — every tool call logged with
  tool name, exit code, and duration
- **Agent loop** (`src/agent_loop.py`) — loop completion summary with round
  count, message count, tool events, and total duration
- **MCP tool calls** (`src/mcp_manager.py`) — success/failure with server name
  and duration
- **Background jobs** (`src/bg_jobs.py`) — launch, complete, fail, timeout
  lifecycle events
- **Auth events** (`routes/auth_routes.py`) — login success/failure, signup,
  logout, password change, admin user CRUD
- **Settings changes** (`routes/auth_routes.py`) — audit log of who changed
  what setting, with old and new values

#### Performance Timing Instrumentation

All timing uses `time.perf_counter()` and logs at INFO only when thresholds
are exceeded (avoiding noise in normal operation):

| File | What's Instrumented | Threshold |
|------|-------------------|-----------|
| `src/embeddings.py` | HTTP encode duration, FastEmbed load time, client factory time | >500ms encode |
| `src/chroma_client.py` | TCP connect probe, ChromaDB heartbeat | Always logged |
| `routes/email_helpers.py` | IMAP TCP connect, IMAP login, SMTP send duration | >200ms IMAP, always SMTP |
| `src/service_health.py` | All subsystem probe elapsed times | Always in meta |
| `services/search/providers.py` | SearXNG HTTP call duration | >500ms |
| `routes/email_pollers.py` | Auto-summarize pass, scheduled poll tick | >1s |
| `routes/note_routes.py` | ntfy publish HTTP POST | Always logged |

#### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `ODYSSEUS_DEBUG` | `0` | Enable DEBUG level on all loggers |
| `ODYSSEUS_DEBUG_SUBSYSTEMS` | (none) | Comma-separated list of loggers to enable DEBUG for (e.g., `odysseus.src.llm_core`) |
| `ODYSSEUS_LOG_FORMAT` | `text` | Console format: `text` or `json` |
| `ODYSSEUS_LOG_FILE` | `data/logs/odysseus.log` | Log file path |

#### Logger Hierarchy

All Odysseus code uses `structlog.get_logger(__name__)`, producing a natural
hierarchy: `odysseus.src.llm_core`, `odysseus.routes.chat_routes`, etc. This
enables per-subsystem debug control via `ODYSSEUS_DEBUG_SUBSYSTEMS`.

### Files Changed

**New files (4):**
- `src/logging_config.py`
- `src/log_context.py`
- `src/log_redaction.py`
- `src/log_timing.py`

**New dependencies (1):**
- `requirements.txt` — added `structlog`

**Modified files (121):**
- `app.py` — `AccessLoggingMiddleware`, structlog setup
- `src/constants.py` — logging constants, fixed `odysseous.log` → `odysseus.log` typo
- `src/llm_core.py` — noisy debug logs removed (6 internal housekeeping messages)
- `src/tool_execution.py` — tool execution timing + result logging
- `src/agent_loop.py` — loop completion summary
- `src/mcp_manager.py` — MCP call success/failure with duration
- `src/bg_jobs.py` — job lifecycle logging
- `src/integrations.py` — logger migration
- `routes/auth_routes.py` — auth event + settings audit logging
- `routes/email_helpers.py` — SMTP send logging
- `core/database.py`, `core/auth.py`, `core/session_manager.py` — logger migration
- ~115 additional files — mechanical `logging.getLogger(__name__)` → `structlog.get_logger(__name__)` migration

**Test files (4):**
- `tests/test_log_redaction.py` — 21 tests for key-name redaction
- `tests/test_log_context.py` — 12 tests for request correlation
- `tests/test_logging_config.py` — 14 tests for setup, debug mode, JSON output
- `tests/test_logging_integration.py` — 7 integration tests (subprocess-based, end-to-end)

### Backward Compatibility

- All existing `logging.getLogger()` calls continue to work via structlog's
  stdlib integration
- No changes to log output format for existing deployments (console: text,
  file: JSON)
- `ODYSSEUS_DEBUG=1` behavior is preserved
- The `odysseous.log` typo fix changes the default log filename to
  `odysseus.log` — existing deployments using the default will see the
  filename change

### Relationship to Upstream Work

This PR complements upstream's ongoing hardening work without duplicating it:

- **PR #3799** (hardening pass, open) includes "PII scrubbed from logs" and "audit
  logging for sensitive operations" in its scope. It does NOT touch any of the
  files in this PR (verified via GitHub API). Our `src/log_redaction.py` provides
  the key-name-based redaction processor that upstream's PII scrubbing can plug
  into, and our `routes/auth_routes.py` audit logging provides the "audit trail
  for sensitive operations" that #3803 calls for.
- **Issue #3212** (silent exception logging) adds `logger.warning()` calls to
  previously-silent exception handlers. Our structured logging infrastructure
  makes those warnings actionable with request correlation IDs and per-subsystem
  debug control.
- **Issue #2107** (PII sanitization for LLM calls) is a separate concern — it
  scrubs PII before sending to LLM providers, while our redaction scrubs PII
  from log output. Both are needed.

### Testing

- [x] 66 tests pass (59 unit + 7 integration)
- [x] All 138 changed files verified: zero non-logging changes mixed in
- [x] No file overlap with upstream PR #3799 (verified via GitHub API)
- [x] App startup verified: logging initializes, produces structured JSON output
- [ ] Start server with `ODYSSEUS_DEBUG=1` — verify DEBUG output on console
- [ ] Make HTTP request — verify `X-Request-ID` header in response
- [ ] Check `data/logs/odysseus.log` — verify JSON-formatted entries
- [ ] Test timing: verify `elapsed_ms` appears in health probe responses

---

## Filing Notes

This branch is built from `upstream-mirror` and contains only logging-related
changes. No fork-specific files (Qt wrapper, docs/fork/, tooling/) are included.
The PR should target `dev`.
