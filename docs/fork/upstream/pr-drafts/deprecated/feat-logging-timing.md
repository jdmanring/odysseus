# PR Draft: feat/logging-timing → odysseus-dev/odysseus:dev

**Branch:** `jdmanring/odysseus:feat/logging-timing`
**Base:** `jdmanring/odysseus:feat/logging-core` (depends on PR #1)
**Issue:** [#31](https://github.com/jdmanring/odysseus/issues/31) (fork tracking)
**Status:** Ready to file after feat/logging-core merges

---

## Title

`feat(logging): performance timing instrumentation for network I/O paths`

---

## Summary
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

## Target branch

- [x] This PR targets **`dev`**, not `main`. All PRs land in `dev`; `main` is curated by the maintainer at each release.

## Linked Issue

Fixes # <!-- [file upstream issue first] -->

## Type of Change

- [ ] Bug fix (non-breaking — fixes a confirmed issue)
- [x] New feature (non-breaking — adds new behaviour)
- [ ] Breaking change (changes or removes existing behaviour)
- [ ] Refactor / cleanup (behaviour unchanged)
- [ ] Documentation only
- [ ] CI / tooling / configuration

## Checklist

- [x] I searched [open issues](https://github.com/odysseus-dev/odysseus/issues) and [open PRs](https://github.com/odysseus-dev/odysseus/pulls) — this is not a duplicate.
- [x] This PR targets `dev`
- [x] My changes are limited to the scope described above — no unrelated refactors or whitespace changes mixed in.
- [x] I actually ran the app (`docker compose up` or `uvicorn app:app`) and verified the change works end-to-end. Type-checks and unit tests are not enough.

### How to Test

**Automated (passing):**
- [x] All 64 tests from `feat/logging-core` pass on this branch (timing changes don't break existing tests)

**Manual verification:**

1. Start the server: `uvicorn app:app --host 0.0.0.0 --port 7000`
2. Hit the health endpoint: `curl http://localhost:7000/api/health | python3 -m json.tool`
3. Confirm the JSON response includes `elapsed_ms` fields in the subsystem probe results (ChromaDB, embeddings, SearXNG).
4. If SearXNG is configured and takes > 500ms to respond, confirm a `search.timing` log entry appears in `data/logs/odysseus.log`.
5. Open the Cookbook tab and start a model download — confirm timing entries appear in the log for the IMAP/SMTP paths if email is configured.
6. Run the agent with a multi-step task — confirm `agent.timing` entries appear in the log on completion with `duration_ms` populated.
7. Start the server with `ODYSSEUS_DEBUG=1` — confirm timing is logged even for fast operations (below the thresholds).
8. Confirm no new test failures: `pytest` should pass all 64+ tests.

---

## Filing Notes

- **File upstream issue first** — draft in `docs/fork/upstream/issue-drafts/feat-logging-timing.md`. Add the issue number to `Fixes #` above before opening the PR.
- Depends on `feat/logging-core` merging upstream first. File the issue now; file the PR after core merges.

## Visual / UI changes

None — no HTML, CSS, or DOM-writing JS was changed.
