# feat(agent): detect gh CLI and inject into system prompt

**Branch:** `feat/gh-cli-detection`
**Type:** Enhancement
**Status:** Ready to file

## Summary

When `gh` is installed and authenticated on the host, inject a GitHub CLI context block
into the agent system prompt so the agent uses `bash` + `gh` for GitHub operations.
Also fixes a keyring access gap that prevented `gh` from working inside the bash tool
on Linux systems using the system keyring.

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
| `src/integrations.py` | `get_github_cli_prompt()`: runs `gh auth status --hostname github.com` (5 s timeout, silently skipped if absent/unauthed); extracts token via `gh auth token` and sets `GH_TOKEN` in process environment for subprocess inheritance; returns a `## GitHub CLI` context block listing common commands |
| `src/agent_loop.py` | Calls `get_github_cli_prompt()` and appends result to agent system prompt |

## How it works

On every prompt build, `get_github_cli_prompt()` runs `gh auth status`. If `gh` is
absent or not authenticated it returns empty string and nothing changes.

When authenticated, the function also runs `gh auth token --hostname github.com` and
sets `os.environ["GH_TOKEN"]` so that subprocesses spawned by the bash tool inherit
the token without needing keyring access (which is unavailable in D-Bus-less subprocess
contexts on Linux).

The agent then sees:

```
## GitHub CLI

`gh` is installed and authenticated as **USERNAME**. For ALL GitHub tasks, use the
`bash` tool and run `gh` commands directly. Do NOT use api_call for GitHub — use bash.

Examples:
  gh repo list
  gh repo list USERNAME --limit 30
  gh issue list --repo owner/repo
  gh issue create --repo owner/repo --title '...' --body '...'
  gh pr list --repo owner/repo
  gh pr view NUMBER --repo owner/repo
  gh api /repos/owner/repo/contents/path
  gh release list --repo owner/repo
```

## How to Test

- [ ] `gh` installed and authenticated on host
- [ ] Server restarted
- [ ] Ask agent "show me my GitHub repos" — it runs `gh repo list` via `bash`
- [ ] Ask agent to create a GitHub issue — it uses `gh issue create`
- [ ] On a host without `gh`, confirm no context block appears and behaviour is unchanged
- [ ] On a host where `gh` authenticates via keyring: confirm `GH_TOKEN` is set in
      the process environment after first prompt build and `gh` commands work in bash

## Visual / UI changes

None — context block appears in agent system prompt only, not in the UI.

## Checklist

- [x] I searched open issues and open PRs — this is not a duplicate.
- [x] This PR targets `dev`
- [x] Changes are limited to the scope described above.
- [x] I ran the app and verified the change works end-to-end.
- [ ] **I am not an LLM agent submitting a bulk PR.** I reviewed and tested this change personally before submitting.

## Filing Notes

- File upstream issue first (draft: `docs/fork/upstream/issue-drafts/feat-gh-cli-detection.md`)
- No screenshots required
