# Upstream PR Draft: perf-mcp-lazy-connect

**Branch:** `perf/mcp-lazy-connect` (from `upstream-mirror`)
**Target:** `pewdiepie-archdaemon/odysseus:dev`
**Fixes:** #_ (file issue-drafts/perf-mcp-lazy-connect.md first, or link #2140)
**Filing notes:** Rebase onto current `dev` and **reconcile with open PR #4812**, which edits
the same `register_builtin_servers` startup-task region. Single concern; one squashed commit.

---

## Title

`perf(mcp): lazy-connect cold built-in MCP servers on first tool call`

## Description

Built-in Python MCP servers are spawned eagerly at startup. Each holds ~48–53 MB RSS, but
`image_gen`, `rag`, and `email` are feature-gated and may never be used in a session — ~150 MB
resident for nothing. This defers the cold servers and connects them on first use.

**Change**
- `src/builtin_mcp.py`: `_EAGER_SERVERS = {"memory"}`. `register_builtin_servers` connects eager
  servers as before; the rest are registered via `mcp_manager.mark_deferred(...)` — a
  `{"status": "deferred"}` entry with **no subprocess spawned**.
- `src/mcp_manager.py`: new `mark_deferred` / `_is_deferred`. In `call_tool`, when there is no
  live session and the server is a deferred built-in, spawn it via the existing
  `_reconnect_builtin` path, cache the session, and proceed. Subsequent calls reuse it.

**Why it's safe**
- Built-in tool descriptions are static in the agent prompt (`get_tool_descriptions_for_prompt`
  skips built-in Python servers; invocation is via the static `_MCP_TOOL_MAP`), so deferring a
  connection does not hide tools from the model — no schema cache required.
- The hook is on actual tool demand, so background/scheduled tool calls spawn the server too.

**Pattern:** established MCP lazy-loading (`mcp-gateway`, `lazy-mcp`), adapted to the in-process
manager rather than vendoring a standalone proxy.

**Cost:** one spawn + import (~hundreds of ms) on first use of a cold feature.
**Out of scope (v1):** idle-unload of unused servers.

## Tests

`tests/test_mcp_lazy_connect.py` (6): deferred status + idempotence (no downgrade of a live
connection); lazy spawn-on-first-call exactly once; no spawn when already connected; eager set
is `{"memory"}`; registration branches eager-vs-deferred.

## Risk

Low–medium. Reuses the proven `_reconnect_builtin` path. Known limitation: no single-flight
guard if two calls race on first use (both may spawn) — matches existing reconnect behavior;
follow-up if measured to matter.
