# Upstream Issue Draft: fix-agent-tool-budget

**File on:** `pewdiepie-archdaemon/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/fix-agent-tool-budget.md`
**Branch:** `fix/agent-tool-budget`
**Type:** Bug

---

## Title

`[Agent] agent_max_tool_calls defaults to 0 — agent mode non-functional out of the box`

---

## Body

**Install method:** Docker / manual Python

**OS / device:** Any

**Steps to Reproduce:**
1. Fresh install — do not change `data/settings.json` or any agent settings.
2. Open the agent interface and send a prompt that requires tool use (e.g. "search the web for recent news about X" or "read my notes about Y").
3. Observe the agent response.

**Expected:** The agent executes tool calls and completes the task.

**Actual:** The agent executes zero tool calls and cannot complete any tool-dependent task. `agent_max_tool_calls` in `src/settings.py` defaults to `0`, which the agent loop interprets as a hard ceiling of zero tool calls per round.

**Logs / Error Output:**
No error is logged. The cap is silently enforced — the agent simply does not call any tools.

**Additional context:** The `0` value appears to be intended as a sentinel meaning "no limit," consistent with how `agent_timeout_secs` uses `0` to mean "no timeout." However, the agent loop implements `agent_max_tool_calls` as a literal ceiling. A value of `0` means no tool calls are permitted. The setting is only functional for users who have already explicitly changed it from the default — which new users have no reason to do, since the default is not documented as "requires manual configuration before agent mode works."
