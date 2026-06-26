# MCP Lazy-Connect — Research & Design Record

**Issue:** [jdmanring/odysseus#111](https://github.com/jdmanring/odysseus/issues/111)
**Branch:** `perf/mcp-lazy-connect` (from `upstream-mirror`)
**Audit finding:** `docs/fork/perf-audit-2026-06.md` §E1
**Date:** 2026-06-25

## Problem (measured)

`register_builtin_servers` spawns all four built-in Python MCP servers at startup,
regardless of use. Measured PSS/Private (idle session, `tooling/mem-probe.py stack`):

| Server | Private RSS | Hot? |
|---|---|---|
| `memory` | ~48 MB | **Yes** — used nearly every session |
| `image_gen` | ~48 MB | No — only when generating an image |
| `rag` | ~48 MB | No — only on a RAG query |
| `email` | ~53 MB | No — only when email is opened |

They share little heap (imports land in each interpreter's private heap), so the three
cold servers are **~150 MB private resident for features that may never be touched**.

## Prior art (this is an established pattern, not a novel idea)

MCP lazy-loading is a well-trodden ecosystem pattern. Most projects frame it around
**context-token reduction** (not advertising all tool *schemas* upfront); the
**memory/CPU win** is the same lever from the other end.

- **[RaiAnsar/mcp-gateway](https://github.com/RaiAnsar/mcp-gateway)** — lazy-loading proxy.
  Mechanism we mirror: *"starts the subprocess, does the MCP handshake, and caches the
  connection; subsequent calls reuse the running process; servers that aren't used never
  start."*
- **[voicetreelab/lazy-mcp](https://github.com/voicetreelab/lazy-mcp)** (Python) — activity-
  driven monitor: sleeps on startup, wakes on first tool call, and after a configurable
  idle timeout (default 5 min) tears the server back down. Reference for the *optional*
  idle-unload (not in v1).
- **[PeterCha90/mcp-lazy-load](https://github.com/petercha90/mcp-lazy-load)**,
  **[lazy-mcp (PyPI)](https://pypi.org/project/lazy-mcp/)** — minimal-surface variants.
- **[anthropics/claude-code#11364](https://github.com/anthropics/claude-code/issues/11364)**
  — the same pattern discussed in Claude Code itself.
- Aggregators: **[FastMCP proxies](https://dev.to/alexretana/streamlining-mcp-management-bundle-multiple-servers-with-fastmcp-proxies-n3i)**
  (same `mcp` package Odysseus uses), **[metatool-ai/metamcp](https://github.com/metatool-ai/metamcp)**.

## Why Odysseus's case is *simpler* than the generic proxies

The token-reduction proxies must solve "how does the model still discover a hidden tool"
(search tools, progressive disclosure). **Odysseus does not have that problem for its
built-ins**, verified in-tree:

- `get_tool_descriptions_for_prompt` / `get_all_openai_schemas` **skip built-in Python
  servers** (`src/mcp_manager.py`: *"Skip builtin Python servers — they're already in the
  agent prompt"*); only the NPX browser server is advertised dynamically.
- Built-in tools are invoked via a **static** `_MCP_TOOL_MAP` (`src/tool_execution.py`) and
  described statically in the agent prompt.

⟹ Deferring a built-in's *connection* does **not** hide its tools from the model. **No tool-
schema cache is needed** — the schema-availability problem that the generic proxies solve
does not exist here. This is the key verification that makes the implementation small.

## Design (chosen)

Mirror the mcp-gateway mechanism inside the existing in-process `McpManager` (we adapt the
pattern; we do not vendor a standalone proxy — consistent with "adopt the primitive, not
the engine"):

1. **`builtin_mcp._EAGER_SERVERS = {"memory"}`.** `register_builtin_servers` connects eager
   servers as before; for the rest it calls `mcp_manager.mark_deferred(server_id, name)` —
   registers a `{"status": "deferred"}` connection **without spawning** the interpreter.
2. **`McpManager.call_tool`** — at the `if not session:` branch, if the server is a deferred
   built-in, call the **existing** `_reconnect_builtin(server_id)` (spawn + handshake), cache
   the session, then proceed. Reuses the proven crash-reconnect path; subsequent calls reuse
   the live session.

### Constraints honored
- **Feature integrity:** tools stay visible (static prompt) — verified above.
- **Background/scheduled demand (audit caution #1):** the hook is on *actual tool demand*
  (`call_tool`), not UI panel state — so a `task_scheduler` job that calls an email tool
  spawns the server correctly, with no UI interaction.
- **First-use latency (caution #2):** one interpreter spawn + import on first call (~hundreds
  of ms). Acceptable for a user-initiated email/image action.
- **Idle-unload (caution #3):** deliberately **out of scope for v1** (lazy-mcp shows it works,
  but it adds re-spawn churn — defer until measured worthwhile).

### Known limitations
- No spawn de-duplication if two tool calls race on first use (both may spawn). This matches
  the *existing* crash-reconnect behavior and is a rare edge; a single-flight guard can be a
  follow-up if measurement shows it matters.

## Upstream status (checked 2026-06-25)
- No upstream PR proposes lazy/deferred MCP startup or process-footprint reduction.
- Maps to open issues **#2140** (eager init blocks UI) and **#3824** (dynamic MCP lifecycle),
  neither with a maintainer-endorsed approach or linked PR.
- ⚠ Open PR **#4812** ("retain startup tasks and reap the npx probe on cancel") edits the same
  `register_builtin_servers` startup-task region — **rebase E1 around it before filing.**
- Per [[feedback_initiative_absent_signal]]: neither buy-in nor rejection ⟹ research (done)
  and implement if worthy (it is). Stage as a clean candidate citing this prior art so a
  maintainer can bless the approach.

## Verification
- `tests/test_mcp_lazy_connect.py` (6): deferred status + idempotence; lazy spawn-on-first-
  call (exactly once); no spawn when already connected; eager set is `{"memory"}`; the
  registration branches eager-vs-deferred.
- Live: `python tooling/mem-probe.py stack` at startup should show only `mcp:memory`
  resident; the cold servers appear after their first use.
