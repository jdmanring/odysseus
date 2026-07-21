# Upstream Issue Draft: fix-workspace-shell-access

**File on:** `odysseus-dev/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/fix-workspace-shell-access.md`
**Branch:** `fix/workspace-shell-access`
**Type:** Bug

**Related upstream context:**
- PR #3665 — introduced the workspace feature and the low-signal + workspace fast path
- PR #4398 — fixed the analogous gap for scheduled task agents (merged 2026-06-16)

---

## Title

`fix(agent): bash/python/web_search absent from tool schemas on low-signal turns when workspace is set and tools are enabled`

---

## Body

**Install method:** Docker / manual Python

**OS / device:** Any

**Steps to Reproduce:**

1. In Agent mode, set a workspace path (workspace pill / `/workspace` command).
2. Enable Shell Access and/or Web Search (toggles in the toolbar).
3. Send a short or vague message — e.g. "help me", "what do we have here", "let's work on this".
4. Observe: the agent replies that it does not have access to `bash`, `python`, or `web_search`.

**Expected:** `bash`, `python`, and `web_search`/`web_fetch` are available when their respective toggles are on, regardless of how specific the opening message is.

**Actual:** The agent correctly reports no access, because those tools are not present in its tool schemas for that turn.

**Root Cause:**

`agent_loop.py` contains a fast path for low-signal turns when a workspace is active (introduced in PR #3665):

```python
if not guide_only and not _relevant_tools and bool(_intent.get("low_signal")):
    if workspace:
        _relevant_tools = set(ALWAYS_AVAILABLE)
        _relevant_tools |= (_DOMAIN_TOOL_MAP["files"] & PLAN_MODE_READONLY_TOOLS)
```

`PLAN_MODE_READONLY_TOOLS` includes `web_search` and `web_fetch` but not `bash` or `python`. `_DOMAIN_TOOL_MAP["files"]` includes `bash` and `python` but not `web_search` or `web_fetch`. The intersection therefore excludes all three. The fast path builds `_relevant_tools` from scratch and never consults `disabled_tools` to infer which tools the user enabled — `allow_bash=true` only prevents `bash` from entering `disabled_tools`, it does not add `bash` to `_relevant_tools`.

The result: on any low-signal turn with an active workspace, `bash`, `python`, and `web_search` are absent from the model's tool schema even when the user has explicitly enabled them.

**Additional context:**

PR #4398 (merged 2026-06-16) fixed the structurally identical problem for scheduled task agents: the task runner built tool sets without ever offering `bash`/`python`, independently of the privilege gate that would have admitted them. The fix here follows the same pattern — consult `disabled_tools` to determine which tools the user enabled, and include them.
