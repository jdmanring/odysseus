# PR Draft: feat/logging → odysseus-dev/odysseus:dev

**Branch:** `feat/logging`
**Issue:** [#31](https://github.com/jdmanring/odysseus/issues/31) (fork tracking)
**Upstream Issues Addressed:**
- [#3803](https://github.com/odysseus-dev/odysseus/issues/3803); PII in logs, no audit trail for sensitive operations
- [#3799](https://github.com/odysseus-dev/odysseus/issues/3799); Hardening pass (PII scrubbed from logs)
**Status:** Ready to file

---

## Title

`feat(logging): structured logging with request correlation, redaction, timing, and JSON output`

---

## Why one PR

The timing callsites added throughout the codebase (`timed_operation()`, `structlog.get_logger()`) are direct callers of the infrastructure introduced in the same commit. Splitting into two PRs leaves one half untest-able in isolation: the infrastructure PR would have no callers so you cannot verify timing output; the callsite PR would import from files that don't exist until the first PR lands. The smallest unit that can be installed, started, and verified end-to-end is the combination; and that is what this PR provides.

---

## Summary

### Problem

Odysseus uses stdlib `logging` throughout (~1410 calls across 115 files, per `grep -rn "logger\." --include="*.py"` on current source) but lacks production-grade logging capabilities. The upstream hardening audit (#3803) explicitly identified:
- "PII (emails, usernames, message bodies) logged at INFO level in several paths"
- "No audit trail for sensitive operations (auth events, vault unlock, admin wipes)"

Additionally, there is no request correlation, no structured output, no per-subsystem debug control, and no timing data; so when users report slow operations, there is no way to determine which subsystem is the bottleneck.

### Solution

Replace stdlib `logging` initialisation with [structlog](https://www.structlog.org/) while preserving full backward compatibility; existing `logging.getLogger()` calls continue to work via structlog's stdlib integration. New code uses `structlog.get_logger()` for bound context. Timing instrumentation is added to the hottest network I/O paths.

---

## New Files

- `src/logging_config.py`: processor pipeline: contextvars binding, sensitive data redaction, JSON file output + text console output, per-subsystem debug control via `ODYSSEUS_DEBUG_SUBSYSTEMS`
- `src/log_context.py`: `contextvars`-based request correlation (request_id, session_key, user_id); bind once in middleware, available in every log call
- `src/log_redaction.py`: key-name-based sensitive data redaction (Sentry-style denylist); matches exact key names, never scans string values
- `src/log_timing.py`: `timed_operation()` context manager for critical-path operations

## Infrastructure Changes

**Access Logging Middleware (`app.py`)**
- Generates a UUID4 `request_id` per request, binds it to contextvars
- Logs method, path, status code, duration at INFO/WARNING/ERROR level
- Returns `X-Request-ID` response header for client-side tracing

**Auth Event Logging (`routes/auth_routes.py`); addresses upstream #3803**
- Login success/failure (with reason: invalid_password, invalid_totp)
- Signup, logout, password change, admin user create/delete
- Every `POST /api/auth/settings` logs actor, key changed, and old → new values

**Environment Variables**

| Variable | Default | Purpose |
|----------|---------|---------|
| `ODYSSEUS_DEBUG` | `0` | Enable DEBUG level on all loggers |
| `ODYSSEUS_DEBUG_SUBSYSTEMS` | (none) | Comma-separated subsystem loggers to enable DEBUG for |
| `ODYSSEUS_LOG_FORMAT` | `text` | Console format: `text` or `json` |
| `ODYSSEUS_LOG_FILE` | `data/logs/odysseus.log` | Log file path |

## Timing Instrumentation

Structured timing added to all major network I/O paths. Logs at INFO only when a threshold is exceeded, avoiding noise in normal operation.

| File | What's Instrumented | Threshold |
|------|-------------------|-----------|
| `src/embeddings.py` | HTTP encode, FastEmbed load, client factory | >500ms encode |
| `src/chroma_client.py` | TCP connect probe, ChromaDB heartbeat | Always logged |
| `routes/email_helpers.py` | IMAP connect/login, SMTP send | >200ms IMAP; always SMTP |
| `src/service_health.py` | All subsystem probe elapsed times | Always in meta |
| `services/search/providers.py` | SearXNG HTTP call | >500ms |
| `routes/email_pollers.py` | Auto-summarize pass, scheduled poll tick | >1s |
| `routes/note_routes.py` | ntfy publish HTTP POST | Always |
| `src/agent_loop.py` | Agent loop completion summary | Always |
| `src/bg_jobs.py` | Background job lifecycle (launch, complete, fail, timeout) | Always |
| `src/mcp_manager.py` | MCP tool call success/failure with duration | Always |
| `src/tool_execution.py` | Tool execution timing with exit code | Always |

## Backward Compatibility

- All existing `logging.getLogger()` calls continue to work via structlog's stdlib integration
- No mass migration; only new code uses `structlog.get_logger()`
- `ODYSSEUS_DEBUG=1` behavior preserved

---

## Files Changed

**New files (4):** `src/logging_config.py`, `src/log_context.py`, `src/log_redaction.py`, `src/log_timing.py`

**New dependencies (1):** `requirements.txt`: added `structlog`

**Modified (infrastructure):** `app.py`, `routes/auth_routes.py`, `src/constants.py`

**Modified (timing callsites):** `src/embeddings.py`, `src/chroma_client.py`, `routes/email_helpers.py`, `src/service_health.py`, `services/search/providers.py`, `routes/email_pollers.py`, `routes/note_routes.py`, `src/agent_loop.py`, `src/bg_jobs.py`, `src/mcp_manager.py`, `src/tool_execution.py`

**Test files (5):** `tests/test_log_redaction.py` (21 tests), `tests/test_log_context.py` (12 tests), `tests/test_logging_config.py` (14 tests), `tests/test_logging_integration.py` (7 tests), `tests/test_chroma_client.py` (updated for timing output)

---

## Target branch

- [x] This PR targets **`dev`**, not `main`.

## Linked Issue

Fixes # <!-- [file upstream issue first; see issue-drafts/feat-logging.md] -->

## Type of Change

- [x] New feature (non-breaking, adds new behaviour)

## Checklist

- [x] I searched open issues and open PRs; this is not a duplicate.
- [x] This PR targets `dev`
- [x] Changes are limited to the scope described above.
- [x] I ran the app and verified the change works end-to-end.
- [ ] **I am not an LLM agent submitting a bulk PR.** I reviewed and tested this change personally before submitting.

## Related upstream work (prior-art search, 2026-07-07)

Searched merged commits and open issues/PRs on `dev`:

- **#5236** (open) *move note domain into `routes/note/` subpackage* — this PR's ntfy-send timing instrumentation lives in `note_routes.py`, which #5236 converts to a subpackage shim (the same refactor already applied to history/gallery/contacts/memory/research). **Coordinate:** rebase onto #5236's layout when it lands — the timing re-homes into `routes/note/`.
- **#5208** (open; issue **#5207**) *sanitize ntfy Title header to ASCII* — touches the same ntfy send path. **Non-conflicting** (header encoding vs. timing log); keep both. Also mind **#5142** (merged) which added the SSRF guard our merge already sits behind.

**Verdict:** non-conflicting but same file(s) — rebase-order matters; note it at file time.

## How to Test

**Automated (passing):**
- `pytest`: 64+ tests pass (unit + integration, including subprocess-based end-to-end)

**Manual verification:**

1. `ODYSSEUS_DEBUG=1 uvicorn app:app --host 0.0.0.0 --port 7000`
2. Verify structured log lines on the console (not bare print statements).
3. `curl -v http://localhost:7000/api/health 2>&1 | grep X-Request-ID`: confirm the header is present.
4. Attempt a login; confirm `auth.login.success` or `auth.login.failure` appears in `data/logs/odysseus.log`.
5. Change a setting; confirm a `settings.audit` log entry appears with the changed key and old/new values.
6. `ODYSSEUS_LOG_FORMAT=json uvicorn app:app ...`: confirm log output is one JSON object per line.
7. Hit the health endpoint: `curl http://localhost:7000/api/health | python3 -m json.tool`: confirm `elapsed_ms` fields appear in subsystem probe results.
8. Run the agent with a multi-step task; confirm `agent.timing` entries with `duration_ms` appear in the log on completion.

---

## Filing Notes

- **File upstream issue first**: draft in `docs/fork/upstream/issue-drafts/feat-logging.md`. Add the issue number to `Fixes #` above before opening the PR.
- Reference upstream #3803 in the PR summary as the hardening audit that identified the PII and audit logging gaps. Note this PR does not address all items in #3803.
- Branch: `jdmanring/odysseus:feat/logging` (previously split into feat/logging-core and feat/logging-timing; combined here because callsites are untestable without the infrastructure).
- **SearXNG query content moved to DEBUG:** `services/search/providers.py` previously logged `query=query[:80]` at INFO alongside the timing entry. Query content (health conditions, legal situations, personal research) is the same category of PII that upstream #3803 flagged. Fix: the `searxng_http` INFO entry now logs only `elapsed_ms` and `status`; a paired `searxng_http_query` DEBUG entry carries the query text. Query content is available when `ODYSSEUS_DEBUG=1` or `ODYSSEUS_DEBUG_SUBSYSTEMS=services.search.providers` — a conscious opt-in, not an always-on exposure.
