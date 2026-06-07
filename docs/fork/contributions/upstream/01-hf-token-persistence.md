# [UPSTREAM] HF Token Persistence Bug

## Problem
When setting the HuggingFace token in Settings → Cookbook (outside the Cookbook tab), the sync call `_syncToServer()` is silently dropped due to a guard that checks if `_envState.servers` is hydrated. Since servers are only hydrated when the Cookbook tab is active, the token is never persisted to `data/cookbook_state.json`.

## Fix
Implement a dedicated `POST /api/cookbook/env/hf-token` endpoint that saves only the token, bypassing the full state sync hydration guard.

## Status
- [ ] Implementation drafted in `docs/fork/upstream-contributions.md`
- [ ] PR ready for upstream `dev` branch
