# Upstream Issue Draft: feat-logging-timing

**File on:** `odysseus-dev/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/feat-logging-timing.md`
**Branch:** `feat/logging-timing`
**Type:** Enhancement
**Dependency:** File after `feat/logging-core` merges upstream

---

## Title

`[Logging] Performance timing instrumentation for network I/O paths`

---

## Body

**Area:** Logging / Observability

**Problem / Motivation:**
When a user reports "the app is slow," there is currently no way to determine which subsystem is the bottleneck without adding temporary debug logging and manually comparing timestamps. Is it the IMAP server connection? ChromaDB? SearXNG? The LLM provider? The agent loop? There is no structured timing data in the logs, no standard keys for filtering or aggregation, and no threshold-based signal for when something is slow vs. normal.

**Proposed Solution:**
`time.perf_counter()` timing instrumentation on the hottest network I/O paths. Each instrumented path logs at INFO level only when a configurable threshold is exceeded — zero noise in normal operation, immediate visibility when something is slow. All timing uses structured keys (`duration_ms`, `elapsed_ms`) so results are filterable with `jq` or ingestable into log aggregation systems.

| Path | What is timed | Threshold |
|------|--------------|-----------|
| `src/embeddings.py` | HTTP encode duration, FastEmbed load, client factory | >500 ms encode |
| `src/chroma_client.py` | TCP connect probe, heartbeat | Always logged |
| `routes/email_helpers.py` | IMAP TCP connect, IMAP login, SMTP send | >200 ms IMAP; always SMTP |
| `src/service_health.py` | All subsystem probe elapsed times | Always in metadata |
| `services/search/providers.py` | SearXNG HTTP call | >500 ms |
| `routes/email_pollers.py` | Auto-summarize pass, scheduled poll tick | >1 s |
| `routes/note_routes.py` | ntfy publish HTTP POST | Always logged |
| `src/agent_loop.py` | Agent loop completion summary | Always logged |
| `src/bg_jobs.py` | Background job lifecycle (launch, complete, fail, timeout) | Always logged |
| `src/mcp_manager.py` | MCP tool call success/failure with duration | Always logged |
| `src/tool_execution.py` | Tool execution timing with exit code | Always logged |

This PR depends on `feat/logging-core` (structured logging infrastructure) and should be filed after that PR merges.

**Alternatives Considered:**
- APM agents (Datadog, New Relic): require external infrastructure and add significant runtime overhead.
- `cProfile` / `py-spy`: profiling tools, not suitable for production instrumentation.
- Threshold-based inline `time.perf_counter()` logging is zero-overhead in normal operation (the `perf_counter()` calls themselves add <1 µs each), requires no external tooling, and integrates naturally with the structured logging system from `feat/logging-core`.
