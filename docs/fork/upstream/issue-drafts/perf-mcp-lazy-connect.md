# Upstream Issue Draft: perf-mcp-lazy-connect

**File on:** `odysseus-dev/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/perf-mcp-lazy-connect.md`
**Branch:** `perf/mcp-lazy-connect`
**Type:** Performance / Enhancement
**Note:** May be foldable into existing issue **#2140** (eager init blocks UI) rather than a
new issue — check with maintainers first. Coordinate with open PR **#4812** (touches the same
`register_builtin_servers` startup-task region).

---

## Title

`perf(mcp): lazy-connect cold built-in MCP servers (image_gen/rag/email) on first use`

---

## Body

**Area:** MCP / startup / performance

**Problem**

`register_builtin_servers` (`src/builtin_mcp.py`) spawns all four built-in Python MCP servers
at startup, regardless of whether they are ever used. Each is a full interpreter with its own
imports — measured at ~48–53 MB RSS each (they share little heap). `memory` is hot in nearly
every session, but `image_gen`, `rag`, and `email` are feature-gated: only exercised when the
user generates an image, runs a RAG query, or opens email. That's **~150 MB resident for
features that may never be touched in a session**, plus the startup CPU to spawn them.

This is the same eager-initialization cost reported in #2140.

**Proposal**

Defer the cold built-ins. Register them as *deferred* at startup (no subprocess spawned) and
connect on the first tool call, reusing the existing `_reconnect_builtin` spawn path. Keep
`memory` eager.

This is the well-established MCP lazy-loading pattern (e.g. `mcp-gateway`, `lazy-mcp`): spawn
the subprocess + handshake on first use, then cache the session so later calls reuse it.

**Why it's safe here**

Built-in tool descriptions are static in the agent prompt — `get_tool_descriptions_for_prompt`
already skips built-in Python servers, and they're invoked via the static `_MCP_TOOL_MAP`. So a
deferred connection does **not** hide the tools from the model; no tool-schema cache is needed.
The connect hook is on actual tool demand (`call_tool`), so a `task_scheduler`/background job
that calls a built-in tool spawns the server correctly without any UI interaction.

**Cost:** one interpreter spawn + import (~hundreds of ms) on first use of a cold feature.

**Out of scope (v1):** idle-unload of an unused server (the `lazy-mcp` idle-timeout pattern) —
left as a follow-up pending measurement.

**Expected:** at startup only `memory` is resident; the cold servers appear after first use.
