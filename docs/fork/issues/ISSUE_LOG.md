# System Issue Log

## [ISSUE-001] Renderer OOM Crash — Blank Page After Long Agent Sessions
**Status:** Resolved-Partial  
**Severity:** High  
**Reported:** User (initially as "UI flashing black")  
**Resolved-by:** 2026-06-06 session  

### Root Cause (confirmed)
Two distinct failure modes, both caused by unbounded DOM growth in `#chat-history`:

1. **Gradual accumulation** — a 20-round agent session built up 40+ message bubbles and tool-call DOM subtrees until the V8 Oilpan C++ heap (manages DOM objects) exhausted its virtual address reservation. The GC freed 419 MB → 16 MB just before the fatal allocation, confirming it was a reservation limit not physical RAM.

2. **Bulk session load** — after restarting, `selectSession()` rendered the entire previous session history at once and ran `hljs.highlightElement()` on every code block. A fixed-size Oilpan allocator pool was exhausted at only 78 MB, 11 minutes after startup.

Both crashes confirmed via V8 log evidence: `ERROR:v8_initializer.cc:844] V8 process OOM (Oilpan: Large allocation. Ran out of reservation)`.

### Evidence
- Crash 1: 2026-06-06 20:51:34, renderer pid 13269, ~52 min uptime, 419 MB heap
- Crash 2: 2026-06-06 22:47:12, renderer pid 13699, ~11 min uptime, 78 MB heap  
- Source: `~/.local/share/sddm/wayland-session.log` (Chromium stderr)

### Fix Applied (Partial)
- **`linux_wrapper.py`** (commit `564dd5c`): `renderProcessTerminated` signal handler auto-reloads on crash; 60s memory monitor; OS-level fd redirect so renderer logs go to `logs/wrapper_system.log`; uvicorn access log enabled to `logs/server_access.log`.

### Fix Applied (Partial) — streamingTTS scope
- **`chat.js`** (commit `9fabdc6`): `streamingTTS` hoisted from `const` inside try to `let` before try — fixes ReferenceError in catch block on every stream error.

### Fix Pending — DOM virtualization
- **Branch:** `fix/dom-oom-virtualization` (in progress)
- `MessageWindow` class with IntersectionObserver load pagination + live pruning
- Detailed plan: `personal_docs/plan-dom-virtualization.md`
- Upstream staging: `docs/fork/contributions/upstream/06-dom-oom-virtualization.md`

---

## [ISSUE-003] External Links / Buttons Don't Navigate in Qt Wrapper
**Status:** Fixed  
**Severity:** Medium  
**Reported:** James (2026-06-08)

### Root Cause
`QWebEnginePage` silently drops two types of navigation:
1. Links/JS that navigate the main frame to a non-localhost URL (no `acceptNavigationRequest` override → Qt falls back to default, which blocks external schemes)
2. `target="_blank"` links and `window.open()` calls → `createWindow()` not overridden, returns `nullptr`, request discarded

### Fix Applied
`linux_wrapper.py`: `OdysseusPage(QWebEnginePage)` subclass added with:
- `acceptNavigationRequest`: intercepts main-frame navigations to non-localhost hosts; opens them via `QDesktopServices.openUrl()` and returns `False` so the app view stays on `localhost`
- `createWindow`: creates a temporary `QWebEnginePage`, connects `urlChanged` to fire `QDesktopServices.openUrl()` on first URL, then deletes the temp page

---

## [ISSUE-004] Tool Results Misattributed as User Messages — Model Treats Them as User Input
**Status:** Open — partial fix on `fix/tool-result-role` (broken for Anthropic)
**Severity:** Medium
**Reported:** James (2026-06-08)

### Problem
`_append_tool_results()` in `src/agent_loop.py` injects tool execution results into the
conversation with `"role": "user"`:

```python
{"role": "user", "content": f"[Tool execution results]\n\n{tool_output_text}"}
```

The model receives tool results as if the *user* typed them. On multi-round tool calls
this causes the model to spend turns analyzing whether the results were injected by the
user rather than accepting them as its own tool outputs. Observed: several wasted turns
and tokens re-reading the results with hedging language ("the user provided...").

### Root Cause
The messages array uses OpenAI-style roles (`"user"`, `"assistant"`, `"system"`, `"tool"`).
Tool result messages are appended with `"role": "user"` — indistinguishable from actual
human input without inspecting the `[Tool execution results]` content prefix.

### Branch: `fix/tool-result-role`
One-line change: `"role": "user"` → `"role": "system"` at `agent_loop.py:1215`.

**Works for:** OpenAI-compatible providers — `"role": "system"` messages appear inline in
the conversation at the correct position, so tool results sit in context exactly where
they happened.

**Broken for Anthropic:** `_build_anthropic_payload()` in `src/llm_core.py` (lines 604–655)
extracts *every* `"role": "system"` message from the conversation and concatenates them
into the top-level Anthropic `system` prompt. After the fix, every round's tool results
are pulled out of the conversation flow and bundled together at the top before the first
message. Anthropic/Claude sees all tool results before the conversation starts, out of
temporal order — worse than the original problem.

### Stale Comment
`agent_loop.py` line ~595 (in `_recent_context_for_retrieval`):
```python
# Skip injected tool-result envelopes — role=user but not human intent.
if not content or content.startswith("[Tool execution results]"):
```
After the fix these messages have `role=system` and are already filtered by the earlier
`if msg.get("role") != "user": continue` check. The behaviour is correct but the comment
becomes misleading.

### Proper Fix Required
Provider-aware approach:
- **OpenAI path**: keep `"role": "system"` (branch is correct)
- **Anthropic path**: do NOT use `"role": "system"` — instead inject as `"role": "user"`
  with unambiguous attribution prefix (e.g. `[Tool execution results — NOT user input]\n\n...`)
  OR handle it inside `_build_anthropic_payload()` similarly to how `"role": "tool"` is
  already handled (converted to an Anthropic `tool_result` content block)
- Update the stale comment in `_recent_context_for_retrieval`

### Upstream Status
Not reported or fixed upstream. Upstream `dev` still uses `"role": "user"` for tool results.
This is a valid upstream contribution candidate once the Anthropic path is correctly handled.
See `docs/fork/upstream/` for contribution workflow.

---

## [ISSUE-002] Project Not Self-Describing for AI Agent Onboarding
**Status:** Open  
**Severity:** Medium  
**Reported:** James (2026-06-07)  

### Problem
When an AI agent starts a new session on this project, it has no intuitive entry point
that tells it: what the project is, what's in progress, what the rules are, and where
to find everything. The agent has to rediscover context from scratch each session —
reading memory files, scanning dirs, looking at git log. This costs time and causes
mistakes (e.g. not knowing aria2c is the aria2c downloader's core tool, not understanding
the upstream contribution workflow without reading CONTRIBUTING.md manually).

The project should have a single top-level orientation document that an agent can read
in the first 30 seconds of a session and immediately know:
- What this repo is and what it does
- The two-repo model (fork vs upstream)
- Active branches and what's on each
- Where the rules live (contribution workflow, working conventions)
- Where in-progress work is tracked
- Key tooling and what it does (aria2c, QWebChannel, etc.)
- What NOT to do (never sudo, never file upstream without authorization)

### Fix Needed
Create `docs/fork/AGENT_CONTEXT.md` — a short, dense orientation document that:
1. Describes the project in 2-3 sentences
2. Lists the two remotes and their roles
3. Maps the branch structure
4. Links to: UPSTREAM_CONTRIBUTION_WORKFLOW.md, testing.md, ISSUE_LOG.md, CHANGELOG.md
5. Explains key tools (aria2c = aria2c downloader via BinManager; QWebChannel = JS↔Python bridge; QWebEngineView = Qt browser wrapper)
6. States the hard rules (no sudo, no upstream filing without James, verify before coding)
7. Lists active work and where to find task tracking

This file should be the FIRST thing any agent reads after MEMORY.md.
