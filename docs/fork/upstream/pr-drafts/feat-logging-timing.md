# PR Draft: feat/logging-timing → pewdiepie-archdaemon/odysseus:dev

**Branch:** `jdmanring/odysseus:feat/logging-timing`
**Base:** `jdmanring/odysseus:feat/logging-core` (depends on PR #1)
**Issue:** [#31](https://github.com/jdmanring/odysseus/issues/31) (fork tracking)
**Status:** Ready to file after feat/logging-core merges

---

## Title

`feat(logging): performance timing instrumentation for network I/O paths`

---

## Description

### Problem

When a user reports "the app is slow," there is no way to determine which subsystem is the bottleneck. Is it the IMAP server? ChromaDB? SearXNG? The LLM provider? Currently, debugging performance issues requires adding temporary debug logging, reproducing the issue, and checking timestamps manually.

### Solution

Add `time.perf_counter()` timing instrumentation to the hottest network I/O paths. Each instrumented path logs at INFO level only when a threshold is exceeded, avoiding log noise in normal operation while making slow endpoints immediately visible.

All timing uses structured keys (`duration_ms`, `elapsed_ms`) so results are filterable with `jq` or ingestable into log aggregation systems.

| File | What's Instrumented | Threshold |
|------|-------------------|-----------|
| `src/embeddings.py` | HTTP encode duration, FastEmbed load time, client factory time | >500ms encode |
| `src/chroma_client.py` | TCP connect probe, ChromaDB heartbeat | Always logged |
| `routes/email_helpers.py` | IMAP TCP connect, IMAP login, SMTP send duration | >200ms IMAP, always SMTP |
| `src/service_health.py` | All subsystem probe elapsed times | Always in meta |
| `services/search/providers.py` | SearXNG HTTP call duration | >500ms |
| `routes/email_pollers.py` | Auto-summarize pass, scheduled poll tick | >1s |
| `routes/note_routes.py` | ntfy publish HTTP POST | Always logged |
| `src/agent_loop.py` | Agent loop completion summary | Always logged |
| `src/bg_jobs.py` | Background job lifecycle (launch, complete, fail, timeout) | Always logged |
| `src/mcp_manager.py` | MCP tool call success/failure with duration | Always logged |
| `src/tool_execution.py` | Tool execution timing with exit code | Always logged |

### Long-term Benefits

1. **Faster incident response:** When a user reports slowness, the first place to check is now the logs. You can see exactly which subsystem is the bottleneck without adding temporary debug logging.

2. **Proactive degradation detection:** The health probe `elapsed_ms` field enables the admin panel to show latency trends over time. A gradually increasing ChromaDB heartbeat or IMAP connect time becomes visible before it causes a user-visible outage.

3. **Capacity planning:** SMTP send duration and SearXNG response time logs provide the data needed to set appropriate timeout values and identify when an external service is degrading.

4. **Zero overhead in normal operation:** Thresholds are set high enough that only genuinely slow operations trigger log entries. The `time.perf_counter()` calls themselves add <1μs per call.

### Files Changed

- `src/embeddings.py` — encode timing, FastEmbed load timing, factory timing
- `src/chroma_client.py` — TCP probe timing, heartbeat timing
- `routes/email_helpers.py` — IMAP connect/login timing, SMTP duration
- `src/service_health.py` — elapsed_ms in all probe results
- `services/search/providers.py` — SearXNG HTTP timing
- `routes/email_pollers.py` — poller cycle timing
- `routes/note_routes.py` — ntfy publish timing
- `src/agent_loop.py` — loop completion summary
- `src/bg_jobs.py` — job lifecycle logging
- `src/mcp_manager.py` — MCP call success/failure with duration
- `src/tool_execution.py` — tool execution timing

### Testing

- [x] All existing tests pass (64 tests on base branch)
- [ ] Verify timing logs appear in live server output under load
- [ ] Verify health probe `elapsed_ms` appears in `/api/health` response

---

## Filing Notes

This PR depends on `feat/logging-core` and should be filed after it merges. It targets `dev`.
