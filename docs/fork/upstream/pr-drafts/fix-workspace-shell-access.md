# PR Draft: fix/workspace-shell-access -> odysseus-dev/odysseus:dev

> **BRANCH RETIRED (2026-08-03).** `fix/workspace-shell-access` (#47) no longer
> exists; the fix is **folded into `develop`** (commit `d8c7fa21`) and
> `tests/test_workspace_web_search_tools.py` passes there.
>
> It was held pending upstream PR **#4366**, which would have pinned
> bash/python/web_search/web_fetch/read_file/write_file/edit_file to
> ALWAYS_AVAILABLE system-wide. **#4366 is CLOSED and did not merge** (verified
> 2026-08-03), so the fork fix is once again the only one, and this is worth
> filing rather than waiting. To file: recreate a clean branch from
> `upstream-mirror`.


**Branch:** `fix/workspace-shell-access`
**Issue:** [#47](https://github.com/jdmanring/odysseus/issues/47) (fork tracking, open, bash/python verified; web_search unverified)
**Status:** Single clean commit. File upstream issue first, fill in `Fixes #___`, then open PR.

---

## Upstream PR title

`fix(agent): include shell/web tools in low-signal+workspace tool set when enabled`

---

## Summary

### Problem

When a workspace is active and Shell Access and/or Web Search are toggled on,
the agent reports no access to `bash`, `python`, or `web_search` for short or
vague opening messages.

PR #3665 introduced a fast path in `agent_loop.py` for low-signal turns when a
workspace is set. It builds `_relevant_tools` from scratch as the intersection
of `_DOMAIN_TOOL_MAP["files"]` and `PLAN_MODE_READONLY_TOOLS`. Neither set
contains both `bash` and `web_search`: `PLAN_MODE_READONLY_TOOLS` has
`web_search` but not `bash`; `_DOMAIN_TOOL_MAP["files"]` has `bash` but not
`web_search`. The intersection therefore excludes all three.

The user-facing toggles (Shell Access, Web Search) only prevent tools from
entering `disabled_tools`: they do not positively add tools to `_relevant_tools`.
The fast path builds `_relevant_tools` from scratch and never consults
`disabled_tools`, so both toggles are silently ignored for every low-signal turn
with an active workspace.

### Fix

In the low-signal + workspace path, consult `disabled_tools` to determine which
tools the user enabled, and add them:

```python
if workspace:
    _relevant_tools = set(ALWAYS_AVAILABLE)
    from src.tool_security import PLAN_MODE_READONLY_TOOLS
    _relevant_tools |= (_DOMAIN_TOOL_MAP["files"] & PLAN_MODE_READONLY_TOOLS)
    if "bash" not in disabled_tools:
        _relevant_tools.add("bash")
    if "python" not in disabled_tools:
        _relevant_tools.add("python")
    if "web_search" not in disabled_tools:
        _relevant_tools.add("web_search")
        _relevant_tools.add("web_fetch")
```

This preserves the conservative read-only default when tools are disabled: if
`bash` or `web_search` is in `disabled_tools` (toggle off, or a privilege check
blocked it), neither tool is added. The existing `blocked_tools_for_owner()` gate
and plan-mode denylist remain authoritative: this fix only affects what is
*offered*, not who is *allowed*, mirroring the approach taken in PR #4398 for
task agents.

### Scope

One file changed: `src/agent_loop.py` (+12 / -5 lines, one code block).
No schema changes, no new settings, no new tools.

---

## How to Test

**Shell Access:**

1. Start Odysseus. Switch to Agent mode.
2. Set any valid workspace path (workspace pill or `/workspace`).
3. Enable Shell Access (shell toggle in the toolbar).
4. Send a vague message: `"help me"`, `"what do we have here"`, `"let's get started"`.
5. **Expected:** the agent uses or acknowledges access to `bash`/`python`.
   **Before this fix:** the agent responds that it has no access to the shell.

6. Disable Shell Access (toggle off). Repeat step 4.
7. **Expected:** `bash` and `python` remain unavailable, the gate holds.

**Web Search:**

8. Enable Web Search (web search toggle in the toolbar). Keep workspace set.
9. Send a vague message: `"what's going on here"`, `"help me out"`.
10. **Expected:** the agent lists `web_search` among its available tools.
    **Before this fix:** the agent reports no web search access.

11. Disable Web Search. Repeat step 9.
12. **Expected:** `web_search` and `web_fetch` remain unavailable, the gate holds.

**Specific requests (regression check):**

13. With Shell Access on and workspace set, send: `"run ls -la"` or `"check git status"`.
14. **Expected:** the agent executes the command. This path worked before and must continue to.

---

## Filing Notes

- File the upstream issue first using `docs/fork/upstream/issue-drafts/fix-workspace-shell-access.md`.
- Fill the upstream issue number into `Fixes #___` in the commit message before opening the PR:
  ```
  git checkout fix/workspace-shell-access
  git commit --amend  # replace Fixes #___ with the real upstream issue number
  git push --force-with-lease origin fix/workspace-shell-access
  ```
- PR targets `odysseus-dev/odysseus:dev`.
- Reference PR #3665 (introduced the fast path) and PR #4398 (parallel fix for tasks) in the PR description body.
