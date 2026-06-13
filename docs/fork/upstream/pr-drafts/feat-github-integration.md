# feat(agent): detect gh CLI and surface in system prompt; fix api_call discoverability

**Branch:** `feat/github-integration`
**Type:** Enhancement / Bug fix
**Status:** Ready to file

## Summary

When `gh` is installed and authenticated on the server, Odysseus now automatically
tells the agent — so the agent uses `bash` + `gh` for GitHub operations instead of
guessing. Also fixes two gaps in the integrations framework and two Settings UI bugs
that affected all presets.

## Target branch

- [x] This PR targets **`dev`**, not `main`.

## Linked Issue

Fixes # <!-- [file upstream issue first] -->

## Type of Change

- [x] New feature (non-breaking — adds new behaviour)
- [x] Bug fix (non-breaking — fixes a confirmed issue)
- [ ] Breaking change
- [ ] Refactor / cleanup
- [ ] Documentation only
- [ ] CI / tooling / configuration

## Problem

**GitHub access:** The agent had `bash` available and `gh` may already be installed and
authenticated on the host. But nothing in the system prompt said so, so the agent didn't
know to use it and produced confused or broken behaviour when asked about GitHub repos.

**`api_call` discoverability:** The `api_call` tool was missing from the RAG embedding
index (`BUILTIN_TOOL_DESCRIPTIONS`). The tool retrieval system had nothing to match it
against, so it was never surfaced when users asked about their configured integrations
(Miniflux, Home Assistant, etc.). Additionally, the tool only accepted the exact key
`"integration"` — models sometimes emit `"integration_name"`, `"integration_id"`, `"name"`,
or `"id"` instead, causing every call to fail with `No integration matching ''`.

**Settings UI (all presets):** Two bugs in the unified integrations form:
1. Selecting a preset with a `base_url` (e.g. Home Assistant) did not auto-fill the
   Base URL field — `_applyPreset` never set `url.value`.
2. Reopening a saved integration showed "Custom (no preset)" in the preset dropdown
   because `preset.value` was never restored from the saved item.

## Solution

### Files changed

| File | Change |
|------|--------|
| `src/integrations.py` | Added `get_github_cli_prompt()`: detects `gh` auth status at prompt-build time, injects a GitHub CLI context block so the agent uses `bash` + `gh` |
| `src/agent_loop.py` | Calls `get_github_cli_prompt()` and appends result to the agent system prompt alongside integrations context |
| `src/tool_index.py` | Added `api_call` to `BUILTIN_TOOL_DESCRIPTIONS` (embedding index); added integration-related keyword hints to `_KEYWORD_HINTS` (`github`, `miniflux`, `rss`, `home assistant`, etc.) |
| `src/tool_implementations.py` | `do_api_call` now accepts `integration_name`, `integration_id`, `name`, `id` as aliases; falls back to the only configured integration when the field is empty and exactly one is configured |
| `static/js/settings.js` | `_applyPreset` now sets `url.value` when preset defines `base_url`; edit form now restores `preset.value` from saved item |

### gh CLI detection

`get_github_cli_prompt()` runs `gh auth status --hostname github.com` (5 s timeout,
no exception propagation). If `gh` is absent or unauthenticated it returns an empty
string and nothing is injected. When authenticated, the agent sees:

```
## GitHub CLI

`gh` is installed and authenticated (as USERNAME). Use the `bash` tool to run
`gh` commands for GitHub — this is faster and more reliable than the api_call
integration:
- `gh repo list` — list repositories
- `gh pr list --repo owner/repo` — list pull requests
...
```

## Checklist

- [x] I searched open issues and open PRs — this is not a duplicate.
- [x] This PR targets `dev`
- [x] My changes are limited to the scope described above.
- [x] I actually ran the app and verified the change works end-to-end.

## How to Test

- [ ] Server restarted after code changes
- [ ] Ask agent "show me my GitHub repos" — it uses `bash` + `gh repo list`, not api_call
- [ ] Ask agent to create a GitHub issue — it uses `gh issue create`
- [ ] Settings → Integrations → Add → select Home Assistant preset → Base URL auto-fills
- [ ] Save an integration with a preset → reopen it → preset dropdown shows preset name (not "Custom")
- [ ] Configure a Miniflux integration → ask agent about unread feeds → `api_call` is used

## Screenshots

No visible UI change. The gh CLI context appears in the agent's system prompt only.
The Settings preset/base_url fix is minor UX — no screenshot needed.

## Notes

- `get_github_cli_prompt()` is pure read — no writes, no side effects, safe to call
  on every prompt build. The subprocess timeout is 5 s; failure is silently swallowed.
- The `api_call` RAG fix requires a server restart so the embedding index rebuilds.
- The `tool_implementations.py` alias fix is defensive — no behaviour change for
  callers that already use the correct `integration` key.

## Filing Notes

- **File upstream issue first** — draft in `docs/fork/upstream/issue-drafts/feat-github-integration.md`
- No screenshots required (no visible UI change)
