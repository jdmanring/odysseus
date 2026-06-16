# PR Draft: fix/workspace-shell-access → pewdiepie-archdaemon/odysseus:dev

**Branch:** `jdmanring/odysseus:fix/workspace-shell-access`
**Issue:** [#47](https://github.com/jdmanring/odysseus/issues/47) (fork tracking, closed — verified)
**Status:** Single clean commit. File upstream issue first, fill in `Fixes #___`, then open PR.

---

## Upstream PR title

`fix(agent): include bash/python in low-signal+workspace tool set when Shell Access is on`

---

## Summary

### Problem

When a workspace is active and Shell Access is toggled on, the agent reports no
access to `bash` or `python` for short or vague opening messages.

PR #3665 introduced a fast path in `agent_loop.py` for low-signal turns when a
workspace is set. It builds `_relevant_tools` from scratch using only
`PLAN_MODE_READONLY_TOOLS` — a read-only allowlist — so `bash` and `python` are
always excluded regardless of the Shell Access toggle.

`allow_bash=true` (Shell Access on) only prevents `bash` from entering
`disabled_tools`. It does not positively add `bash` to `_relevant_tools`. The
fast path never consults `disabled_tools` to infer what the user enabled, so
Shell Access is silently ignored for every low-signal turn with an active
workspace.

### Fix

In the low-signal + workspace path, add `bash` and `python` to `_relevant_tools`
when they are not in `disabled_tools`:

```python
if workspace:
    _relevant_tools = set(ALWAYS_AVAILABLE)
    from src.tool_security import PLAN_MODE_READONLY_TOOLS
    _relevant_tools |= (_DOMAIN_TOOL_MAP["files"] & PLAN_MODE_READONLY_TOOLS)
    if "bash" not in disabled_tools:
        _relevant_tools.add("bash")
    if "python" not in disabled_tools:
        _relevant_tools.add("python")
```

This preserves the conservative read-only default for users who have not enabled
Shell Access: if `bash` is in `disabled_tools` (Shell Access off, or a
non-admin privilege check blocked it), neither tool is added. The existing
`blocked_tools_for_owner()` gate and plan-mode denylist remain authoritative —
this fix only affects what is *offered*, not who is *allowed*, mirroring the
approach taken in PR #4398 for task agents.

### Scope

One file changed: `src/agent_loop.py` (+9 / -5 lines, one code block).
No schema changes, no new settings, no new tools.

---

## How to Test

1. Start Odysseus. Switch to Agent mode.
2. Set any valid workspace path (workspace pill or `/workspace`).
3. Enable Shell Access (shell toggle in the toolbar).
4. Send a vague message: `"help me"`, `"what do we have here"`, `"let's get started"`.
5. **Expected:** the agent uses or acknowledges access to `bash`/`python`.
   **Before this fix:** the agent responds that it has no access to the shell.

6. Disable Shell Access (toggle off). Repeat step 4.
7. **Expected:** `bash` and `python` remain unavailable — the gate holds.

8. With Shell Access on and workspace set, send a specific shell request:
   `"run ls -la"` or `"check git status"`.
9. **Expected:** the agent executes the command. This path worked before the fix
   and must continue to work.

---

## Filing Notes

- File the upstream issue first using `docs/fork/upstream/issue-drafts/fix-workspace-shell-access.md`.
- Fill the upstream issue number into `Fixes #___` in the commit message before opening the PR:
  ```
  git checkout fix/workspace-shell-access
  git commit --amend  # replace Fixes #___ with the real upstream issue number
  git push --force-with-lease origin fix/workspace-shell-access
  ```
- PR targets `pewdiepie-archdaemon/odysseus:dev`.
- Reference PR #3665 (introduced the fast path) and PR #4398 (parallel fix for tasks) in the PR description body.
