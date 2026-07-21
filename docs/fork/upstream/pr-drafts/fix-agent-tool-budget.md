# PR Draft: fix/agent-tool-budget → odysseus-dev/odysseus:dev

**Branch:** `fix/agent-tool-budget`
**Issue:** [#10](https://github.com/jdmanring/odysseus/issues/10) (fork tracking)
**Status:** Ready to file

---

## Title

`fix: change agent_max_tool_calls default from 0 to 20`

---

## Summary
### Problem

`agent_max_tool_calls` defaults to `0` in `src/settings.py`. The agent loop in
`chat_routes.py` reads this as `_tool_budget = int(get_setting("agent_max_tool_calls", 0))`
and passes it to the agent as `max_tool_calls=0`. The budget check in the loop is:

```python
if max_tool_calls > 0 and total_tool_calls >= max_tool_calls:
```

When `max_tool_calls` is `0`, this condition is never true; the budget check is
bypassed entirely. **`0` means unlimited.** A fresh Odysseus install gives agents no
per-session tool call cap at all.

### Why unlimited is the wrong default

**Runaway tool execution risk.** Each "tool call" in the budget counter is one tool
execution; a bash command, a web search, an MCP tool invocation, an email poll. A model
that emits multiple tool blocks in a single response can execute all of them in one
round; there is no per-round tool count limit. An agent doing 20 rounds with 5 tool
blocks per round executes 100 tool calls. Some of those tools make their own external
service calls (SearXNG searches, email API polling, ntfy push requests). With no budget
cap, there is nothing to stop runaway execution if a model loops or hallucinates repeated
tool calls.

The codebase acknowledges this risk in a comment in `agent_loop.py`: *"Small models
(e.g. deepseek-v4-flash) can get stuck firing the same tool call over and over with no
text — burns all 20 rounds, looks like the chat 'died'."* The existing loop-breaker only catches repeated
identical calls. A model that varies its calls slightly continues unchecked. The budget
cap is the general-purpose backstop.

**LLM API cost.** Each round also makes one LLM API call. `agent_max_rounds=20` caps
this at 20 calls per session. That cap is effective only if all 20 rounds are not spent
on runaway tool loops; which requires a working tool budget to prevent the model from
spending every round exclusively executing tools.

**Consistency with `agent_max_rounds`.** The companion setting `agent_max_rounds`
defaults to `20`: a sensible cap on round loops. `agent_max_tool_calls` at `0`
(unlimited) is inconsistent: rounds are capped but tool executions within them are not.
`20` tool calls matches `20` rounds and creates a coherent pair of budgets.

**Misleading UI value.** Users who open Settings → Agent and see `0` next to
`Max tool calls` reasonably interpret it as "zero calls; tool use is disabled." They
set it to some positive number (20, 50, 100) not realising that doing so actually
*reduces* the agent's freedom from unlimited to whatever they typed. The default looks
like a misconfiguration that needs fixing even when it is not.

### Fix

```diff
-    "agent_max_tool_calls": 0,
+    "agent_max_tool_calls": 20,
```

`20` matches `agent_max_rounds`, makes the two budgets consistent, and gives users a
clear starting point to tune from. Existing installs with a stored value are unaffected.

## Target branch

- [x] This PR targets **`dev`**, not `main`. All PRs land in `dev`; `main` is curated by the maintainer at each release.

## Linked Issue

Fixes # <!-- [file upstream issue first] -->

## Type of Change

- [x] Bug fix (non-breaking, fixes a confirmed issue)
- [ ] New feature (non-breaking, adds new behaviour)
- [ ] Breaking change (changes or removes existing behaviour)
- [ ] Refactor / cleanup (behaviour unchanged)
- [ ] Documentation only
- [ ] CI / tooling / configuration

## Checklist

- [x] I searched [open issues](https://github.com/odysseus-dev/odysseus/issues) and [open PRs](https://github.com/odysseus-dev/odysseus/pulls); this is not a duplicate.
- [x] This PR targets `dev`
- [x] My changes are limited to the scope described above; no unrelated refactors or whitespace changes mixed in.
- [x] I actually ran the app (`docker compose up` or `uvicorn app:app`) and verified the change works end-to-end. Type-checks and unit tests are not enough.
- [ ] **I am not an LLM agent submitting a bulk PR.** I reviewed and tested this change personally before submitting.

### How to Test

1. Start Odysseus on a fresh install (or clear `data/settings.json` to reset to defaults).
2. Open the agent interface and send a prompt that requires tool use (e.g., "search the web for X" or "read my notes about Y").
3. Confirm the agent executes tool calls successfully. After 20 tool calls in the session, confirm a `budget_exceeded` event fires and the agent stops cleanly rather than looping indefinitely.
4. Check Settings → Agent; confirm `agent_max_tool_calls` defaults to `20` (not `0`).
5. For existing installs with a previously stored non-zero value: confirm that stored value is preserved (the default is not overwritten on upgrade).

---

## Filing Notes

- One commit, no squash needed.
- **File upstream issue first**: draft in `docs/fork/upstream/issue-drafts/fix-agent-tool-budget.md`. Add the issue number to `Fixes #` above before opening the PR.

## Visual / UI changes

None; no HTML, CSS, or DOM-writing JS was changed.
