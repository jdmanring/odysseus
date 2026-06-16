# Upstream Issue Draft: fix-workspace-shell-access

**File on:** `pewdiepie-archdaemon/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/fix-workspace-shell-access.md`
**Branch:** `fix/workspace-shell-access`
**Type:** Bug

**Related upstream context:**
- PR #3665 — introduced the workspace feature and the low-signal + workspace fast path
- PR #4398 — fixed the analogous gap for scheduled task agents (merged 2026-06-16)

---

## Title

`fix(agent): bash/python absent from tool schemas on low-signal turns when workspace is set and Shell Access is enabled`

---

## Body

**Install method:** Docker / manual Python

**OS / device:** Any

**Steps to Reproduce:**

1. In Agent mode, set a workspace path (workspace pill / `/workspace` command).
2. Enable Shell Access (the shell toggle in the toolbar).
3. Send a short or vague message — e.g. "help me", "what do we have here", "let's work on this".
4. Observe: the agent replies that it does not have access to `bash` or `python`.

**Expected:** `bash` and `python` are available when Shell Access is on, regardless of how specific the opening message is.

**Actual:** The agent correctly reports no shell access, because `bash` and `python` are not present in its tool schemas for that turn.

**Root Cause:**

`agent_loop.py` contains a fast path for low-signal turns when a workspace is active (introduced in PR #3665):

```python
if not guide_only and not _relevant_tools and bool(_intent.get("low_signal")):
    if workspace:
        _relevant_tools = set(ALWAYS_AVAILABLE)
        _relevant_tools |= (_DOMAIN_TOOL_MAP["files"] & PLAN_MODE_READONLY_TOOLS)
```

`PLAN_MODE_READONLY_TOOLS` does not include `bash` or `python`, so this path explicitly excludes them. `allow_bash=true` (Shell Access on) only prevents `bash` from entering `disabled_tools` — it does not positively add `bash` to `_relevant_tools`. The fast path builds `_relevant_tools` from scratch and never consults `disabled_tools` to infer what the user enabled.

The result: on any low-signal turn with an active workspace, the model's tool schema never contains `bash` or `python`, even when Shell Access is explicitly on.

**Additional context:**

PR #4398 (merged 2026-06-16) fixed the structurally identical problem for scheduled task agents: the task runner built tool sets without ever offering `bash`/`python`, independently of the privilege gate that would have admitted them. The fix here follows the same pattern — consult `disabled_tools` to determine whether the shell tools were admitted, and include them if so.
