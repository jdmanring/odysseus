# [UPSTREAM] agent_max_tool_calls Defaults to 0 — Agent Mode Non-Functional Out of Box

## Status
- Issue filed: Not yet filed
- PR opened: Not yet opened
- Fix in fork: Applied — `data/settings.json` sets `agent_max_tool_calls` to 20

## Notes
Single settings default change. No visual change. Confirm the fix doesn't conflict with
any per-user settings migration before filing.

---

## Staged Issue
<!-- James: open https://github.com/pewdiepie-archdaemon/odysseus/issues/new?template=bug_report.yml and paste below -->

**Steps to Reproduce**

1. Install Odysseus on a clean instance (no prior `data/settings.json`).
2. Switch the chat interface to Agent Mode.
3. Send a message that requires tool use (e.g. "Search the web for…").

**Expected Behaviour**

The agent executes tools up to the configured maximum and returns a result.

**Actual Behaviour**

The agent proposes tool calls but never executes any of them. The LLM output includes
tool invocations but the execution engine refuses them. The response appears as if the
agent is thinking without acting.

**Root Cause**

`agent_max_tool_calls` defaults to `0` in the initial `settings.json`. A budget of 0
means the agent loop approves zero tool executions per turn — every proposed tool call
is rejected by the budget check. This effectively disables Agent Mode for all new
installations.

**Proposed Fix**

Change the default value of `agent_max_tool_calls` to a reasonable number (e.g. 20).
This matches expected behavior: users who explicitly enable Agent Mode expect agents
to use tools.

**Install Method:** Manual Python install

**OS:** Linux

**Willing to submit a fix:** Yes — I can open a PR

---

## Staged PR
<!-- James: file the issue first, get the number, fill in Fixes #NNN below, then open PR -->

### Summary

`agent_max_tool_calls` defaults to `0` in `settings.json`, which silently disables
all tool execution even when Agent Mode is active. New users enabling Agent Mode get
no tools, no error message, and no explanation. Fix: change the default to `20`.

### Target branch
- [x] This PR targets **`dev`**, not `main`.

### Linked Issue

Fixes #

### Type of Change
- [x] Bug fix (non-breaking — fixes a confirmed issue)

### Checklist
- [x] Searched open issues and open PRs — not a duplicate
- [x] Targets `dev`
- [x] Changes limited to described scope
- [ ] App run locally, Agent Mode verified with tool use on a fresh settings.json *(must do before filing)*

### How to Test

1. Delete or reset `data/settings.json` to defaults.
2. Restart Odysseus.
3. Switch to Agent Mode and send a web-search request.
4. Confirm the agent executes the search tool and returns results.
5. Confirm `agent_max_tool_calls` is now `20` in the settings panel.

### Visual / UI changes

None — settings default value change only.
