# Upstream Issue Draft: fix-agent-tool-budget

**File on:** `odysseus-dev/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/fix-agent-tool-budget.md`
**Branch:** `fix/agent-tool-budget`
**Type:** Bug

---

## Title

`[Agent] agent_max_tool_calls defaults to 0 — no tool call budget on fresh installs`

---

## Body

**Install method:** Docker / manual Python

**OS / device:** Any

**Steps to Reproduce:**
1. Fresh install — do not change `data/settings.json` or any agent settings.
2. Open the agent interface and send a complex prompt designed to trigger many tool calls (e.g. "research X thoroughly and summarise the latest findings").
3. Observe the agent.

**Expected:** The agent runs tool calls up to a sensible cap, then stops cleanly.

**Actual:** The agent runs unlimited tool calls with no cap. The budget check in `chat_routes.py` is:
```python
_tool_budget = int(get_setting("agent_max_tool_calls", 0))
```
and in `agent_loop.py`:
```python
if max_tool_calls > 0 and total_tool_calls >= max_tool_calls:
```
When `agent_max_tool_calls` is `0`, the condition `max_tool_calls > 0` is False and the check never fires. **`0` means unlimited.** A stuck or runaway agent can make hundreds of API calls in a single session with nothing to stop it.

**Additional context:**

The Settings UI displays `0` next to "Max tool calls," which users reasonably read as "zero calls allowed — tool use disabled." This causes confusion: users set it to a positive number thinking they are enabling tool use, when they are actually imposing a cap that did not previously exist.

The companion setting `agent_max_rounds` defaults to `20`, giving each conversation a sensible round limit. `agent_max_tool_calls` at `0` (unlimited) is inconsistent with this: rounds are capped but tool calls within each round are not, leaving the door open for significant runaway cost in multi-tool-call-per-round scenarios.

**Suggested fix:** Default to `20` to match `agent_max_rounds`, make both budgets consistent, and prevent unbounded tool call accumulation on fresh installs.
