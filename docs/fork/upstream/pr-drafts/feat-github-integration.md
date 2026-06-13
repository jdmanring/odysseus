# feat(agent): detect gh CLI and surface in system prompt; fix api_call discoverability

**Branch:** `feat/github-integration`
**Type:** Enhancement / Bug fix
**Status:** Ready to file

## Summary

When `gh` is installed and authenticated on the host, Odysseus now tells the agent —
so the agent uses `bash` + `gh` for GitHub operations automatically. Also fixes
`api_call` not appearing in tool retrieval, and two Settings UI bugs affecting all presets.

## Target branch

- [x] This PR targets **`dev`**, not `main`.

## Linked Issue

Fixes # <!-- [file upstream issue first] -->

## Type of Change

- [x] New feature (non-breaking)
- [x] Bug fix (non-breaking)

## Files changed

| File | Change |
|------|--------|
| `src/integrations.py` | `get_github_cli_prompt()`: runs `gh auth status` at prompt-build time; injects a `## GitHub CLI` block with common commands when authenticated |
| `src/agent_loop.py` | Calls `get_github_cli_prompt()` and appends result to agent system prompt |
| `src/tool_index.py` | Adds `api_call` to `BUILTIN_TOOL_DESCRIPTIONS`; adds integration keyword hints to `_KEYWORD_HINTS` |
| `src/tool_implementations.py` | `do_api_call` accepts `integration_name`/`integration_id`/`name`/`id` as aliases; single-integration fallback when field is empty |
| `static/js/settings.js` | `_applyPreset` sets `url.value` when preset defines `base_url`; edit form restores `preset.value` from saved item |

## How to Test

- [ ] Ask agent "show me my GitHub repos" — it runs `gh repo list` via `bash`
- [ ] Ask agent to create a GitHub issue — it runs `gh issue create`
- [ ] Settings → Integrations → Add → select Home Assistant preset → Base URL auto-fills
- [ ] Save an integration → reopen it → preset dropdown shows preset name, not "Custom"
- [ ] Configure Miniflux → ask about unread feeds → `api_call` is used correctly

## Visual / UI changes

No visible change. The `## GitHub CLI` block appears in the agent system prompt only.
The Settings preset/base-url fix is minor UX — no screenshot needed.

## Checklist

- [x] I searched open issues and open PRs — this is not a duplicate.
- [x] This PR targets `dev`
- [x] Changes are limited to the scope described above.
- [x] I ran the app and verified the change works end-to-end.
- [ ] **I am not an LLM agent submitting a bulk PR.** I reviewed and tested this change personally before submitting.

## Filing Notes

- File the upstream issue first (draft: `docs/fork/upstream/issue-drafts/feat-github-integration.md`)
- No screenshots required
