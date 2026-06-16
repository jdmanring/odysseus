# feat(agent): detect gh CLI and inject into system prompt

**Branch:** `feat/gh-cli-detection`
**Type:** Enhancement
**Status:** Ready to file

## Summary

### Problem

Developers using Odysseus's agent mode for GitHub tasks; PR review, issue triage,
release management, code search across repos; have no working path out of the box.
Two separate failures block them.

**1; No GitHub context in the agent prompt.** Without knowing `gh` is available, the
agent tries workarounds: it may attempt to construct `curl` calls to the GitHub REST
API, ask the user for a PAT, or refuse GitHub tasks entirely. Even if the agent tries
`gh`, it does not know the authenticated username, the available commands, or that `gh`
should be preferred over raw API calls. Developers have to manually instruct the agent
on every session.

**2; GH_TOKEN not available in bash subprocesses on Linux.** On Linux systems that
store authentication in the system keyring (GNOME Keyring, KWallet, or any
secret-service provider), `gh auth status` succeeds at the command line because the
terminal has a D-Bus session. When the Odysseus server spawns a subprocess via the bash
tool, that subprocess does not inherit the D-Bus session. `gh` inside the bash tool
falls back to looking for `GH_TOKEN` in the environment, finds nothing, and fails with
an authentication error. The user's `gh` installation appears broken from the agent's
perspective even though it works perfectly from the terminal.

### Solution

When `gh` is installed and authenticated on the host, inject a GitHub CLI context block
into the agent system prompt so the agent uses `bash` + `gh` for GitHub operations.
Also fixes the keyring access gap by extracting the token via `gh auth token` at prompt
build time and setting `GH_TOKEN` in the process environment for subprocess inheritance.

## Target branch

- [x] This PR targets **`dev`**, not `main`.

## Linked Issue

Fixes # <!-- [file upstream issue first] -->

## Type of Change

- [x] New feature (non-breaking)
- [x] Bug fix (non-breaking)

## Files changed

- `src/integrations.py`: `get_github_cli_prompt()`: runs `gh auth status --hostname github.com` (5 s timeout, no-op if absent/unauthed); extracts token via `gh auth token` and sets `GH_TOKEN` in process env for subprocess inheritance; returns a `## GitHub CLI` context block listing common commands
- `src/agent_loop.py`: calls `get_github_cli_prompt()` and appends result to agent system prompt
- `tests/test_gh_cli_detection.py` (new); 12 behavioral tests using `monkeypatch` on `shutil.which` and `subprocess.run`

## Tests

**`tests/test_gh_cli_detection.py`**: 12 tests covering all guarded paths:

- **Not installed** (2 tests): `shutil.which` returns `None` → returns `""` and returns a `str`
- **Auth failure** (2 tests): `gh auth status` exits non-zero → returns `""`;
  subprocess raises `OSError` → returns `""` (exception guard)
- **Authenticated** (7 tests): both guards pass → returns a non-empty string
  containing "GitHub CLI", the authenticated username, and example commands
  (`gh repo list`, `gh pr list`, `gh issue create`); `GH_TOKEN` is set from
  `gh auth token` when not already present; existing `GH_TOKEN` is not overwritten;
  username falls back to "you" when not parseable from `gh auth status` output

Uses `monkeypatch.setattr` on `shutil.which` and `subprocess.run` (OS-boundary
functions). No network access required.

## How it works

On the first prompt build after server start, `get_github_cli_prompt()` runs `gh auth status` and caches the result. Subsequent calls return the cached value without spawning subprocesses. If `gh` is absent or not authenticated it returns empty string and nothing changes.

When authenticated, the function also runs `gh auth token --hostname github.com` and
sets `os.environ["GH_TOKEN"]` so that subprocesses spawned by the bash tool inherit
the token without needing keyring access (which is unavailable in D-Bus-less subprocess
contexts on Linux). Note: `os.environ` is process-wide; `GH_TOKEN` is therefore
inherited by all subprocesses, not only agent bash calls. On single-user installations
this is the correct behavior. Multi-tenant deployments should be aware of the scope.

The agent then sees:

```
## GitHub CLI

`gh` is installed and authenticated as **USERNAME**. For ALL GitHub tasks, use the
`bash` tool and run `gh` commands directly. Do NOT use api_call for GitHub; use bash.

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
- [ ] Ask agent "show me my GitHub repos"; it runs `gh repo list` via `bash`
- [ ] Ask agent to create a GitHub issue; it uses `gh issue create`
- [ ] On a host without `gh`, confirm no context block appears and behaviour is unchanged
- [ ] On a host where `gh` authenticates via keyring: confirm `GH_TOKEN` is set in
      the process environment after first prompt build and `gh` commands work in bash

## Visual / UI changes

None; context block appears in agent system prompt only, not in the UI.

## Checklist

- [x] I searched open issues and open PRs; this is not a duplicate.
- [x] This PR targets `dev`
- [x] Changes are limited to the scope described above.
- [x] I ran the app and verified the change works end-to-end.
- [ ] **I am not an LLM agent submitting a bulk PR.** I reviewed and tested this change personally before submitting.

## Filing Notes

- File upstream issue first (draft: `docs/fork/upstream/issue-drafts/feat-gh-cli-detection.md`)
- No screenshots required
