# PR Draft: fix/agent-tool-budget → pewdiepie-archdaemon/odysseus:dev

**Branch:** `jdmanring/odysseus:fix/agent-tool-budget`
**Issue:** [#10](https://github.com/jdmanring/odysseus/issues/10) (fork tracking)
**Status:** Ready to file

---

## Title

`fix: change agent_max_tool_calls default from 0 to 20`

---

## Summary
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

## Target branch

- [x] This PR targets **`dev`**, not `main`. All PRs land in `dev`; `main` is curated by the maintainer at each release.

## Linked Issue

Fixes # <!-- [file upstream issue first] -->

## Type of Change

- [x] Bug fix (non-breaking — fixes a confirmed issue)
- [ ] New feature (non-breaking — adds new behaviour)
- [ ] Breaking change (changes or removes existing behaviour)
- [ ] Refactor / cleanup (behaviour unchanged)
- [ ] Documentation only
- [ ] CI / tooling / configuration

## Checklist

- [x] I searched [open issues](https://github.com/pewdiepie-archdaemon/odysseus/issues) and [open PRs](https://github.com/pewdiepie-archdaemon/odysseus/pulls) — this is not a duplicate.
- [x] This PR targets `dev`
- [x] My changes are limited to the scope described above — no unrelated refactors or whitespace changes mixed in.
- [x] I actually ran the app (`docker compose up` or `uvicorn app:app`) and verified the change works end-to-end. Type-checks and unit tests are not enough.
- [ ] **I am not an LLM agent submitting a bulk PR.** I reviewed and tested this change personally before submitting.

### How to Test

1. Start Odysseus on a fresh install (or clear `data/settings.json` to reset to defaults).
2. Open the agent interface and send a prompt that requires tool use (e.g., "search the web for X" or "read my notes about Y").
3. Confirm the agent executes tool calls and completes the task without hitting a zero-call cap.
4. Check Settings → Agent — confirm `agent_max_tool_calls` defaults to `20` (not `0`).
5. For existing installs with a previously stored non-zero value: confirm that stored value is preserved (the default is not overwritten on upgrade).

---

## Filing Notes

- One commit, no squash needed.
- **File upstream issue first** — draft in `docs/fork/upstream/issue-drafts/fix-agent-tool-budget.md`. Add the issue number to `Fixes #` above before opening the PR.

## Visual / UI changes

None — no HTML, CSS, or DOM-writing JS was changed.
