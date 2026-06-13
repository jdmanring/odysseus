# PR Draft: fix/agent-tool-budget → pewdiepie-archdaemon/odysseus:dev

**Branch:** `jdmanring/odysseus:fix/agent-tool-budget`
**Issue:** [#10](https://github.com/jdmanring/odysseus/issues/10) (fork tracking)
**Status:** Ready to file

---

## Title

`fix: change agent_max_tool_calls default from 0 to 20`

---

## Description

### Problem

`agent_max_tool_calls` defaults to `0` in `src/settings.py`. A value of 0
means the agent is allowed zero tool calls per round, making agent mode
non-functional out of the box for any user who has not explicitly changed this
setting. The setting comment acknowledges that other values are bounded to
`[60, 86400]` (for the timeout), suggesting the intent was a sentinel meaning
"unlimited" — but the agent loop interprets 0 as a hard cap of zero.

### Fix

Change the default in `DEFAULT_SETTINGS` from `0` to `20`:

```diff
-    "agent_max_tool_calls": 0,
+    "agent_max_tool_calls": 20,
```

`20` matches `agent_max_rounds` and is a reasonable default that allows
multi-step agentic runs while still bounding runaway loops. Users can raise or
lower it in Settings.

### How to Test

1. Start Odysseus on a fresh install (or clear `data/settings.json` to reset to defaults).
2. Open the agent interface and send a prompt that requires tool use (e.g., "search the web for X" or "read my notes about Y").
3. Confirm the agent executes tool calls and completes the task without hitting a zero-call cap.
4. Check Settings → Agent — confirm `agent_max_tool_calls` defaults to `20` (not `0`).
5. For existing installs with a previously stored non-zero value: confirm that stored value is preserved (the default is not overwritten on upgrade).

---

## Filing Notes (James)

- One commit, no squash needed.
- File issue on `pewdiepie-archdaemon/odysseus` first; add its number here
  before opening the PR.
