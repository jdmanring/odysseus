# [UPSTREAM] Agent Tool Budget Default

## Problem
The default value for `agent_max_tool_calls` in `settings.json` is 0, which disables tool execution by default even in "Agent Mode."

## Fix
Update the default value in `settings.json` to 20.

## Status
- [ ] Identified
- [ ] PR ready for upstream `dev` branch
