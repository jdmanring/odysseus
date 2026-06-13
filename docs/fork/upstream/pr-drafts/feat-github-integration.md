# feat(agent): detect gh CLI and surface in system prompt

**Branch:** `feat/github-integration`
**Type:** Enhancement
**Status:** Ready to file

## Summary

When `gh` is installed and authenticated on the host, inject a GitHub CLI context block
into the agent system prompt so the agent uses `bash` + `gh` for GitHub operations.

## Target branch

- [x] This PR targets **`dev`**, not `main`.

## Linked Issue

Fixes # <!-- [file upstream issue first] -->

## Type of Change

- [x] New feature (non-breaking)

## Files changed

| File | Change |
|------|--------|
| `src/integrations.py` | `get_github_cli_prompt()`: runs `gh auth status` (5 s timeout, silently skipped if absent/unauthed); returns a `## GitHub CLI` context block listing common commands |
| `src/agent_loop.py` | Calls `get_github_cli_prompt()` and appends result to agent system prompt |

## How it works

On every prompt build, `get_github_cli_prompt()` runs `gh auth status --hostname github.com`.
If `gh` is absent or not authenticated it returns empty string and nothing changes.
When authenticated the agent sees:

```
## GitHub CLI

`gh` is installed and authenticated (as USERNAME). Use the `bash` tool to run
`gh` commands for GitHub:
- `gh repo list`
- `gh pr list --repo owner/repo`
- `gh issue create ...`
...
```

## How to Test

- [ ] `gh` installed and authenticated on host
- [ ] Server restarted
- [ ] Ask agent "show me my GitHub repos" — it runs `gh repo list` via `bash`
- [ ] Ask agent to create a GitHub issue — it uses `gh issue create`
- [ ] On a host without `gh`, confirm no context block appears and behaviour is unchanged

## Visual / UI changes

None — context block appears in agent system prompt only, not in the UI.

## Checklist

- [x] I searched open issues and open PRs — this is not a duplicate.
- [x] This PR targets `dev`
- [x] Changes are limited to the scope described above.
- [x] I ran the app and verified the change works end-to-end.
- [ ] **I am not an LLM agent submitting a bulk PR.** I reviewed and tested this change personally before submitting.

## Filing Notes

- File upstream issue first (draft: `docs/fork/upstream/issue-drafts/feat-github-integration.md`)
- No screenshots required
