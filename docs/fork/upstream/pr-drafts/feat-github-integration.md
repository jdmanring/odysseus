# feat(integrations): add GitHub preset for agent API access

**Branch:** `feat/github-integration`
**Type:** Enhancement
**Status:** Ready to file

## Summary

Adds a **GitHub** preset to the integrations framework so users can give the agent access to the GitHub REST API. Once configured, the agent can create issues, list pull requests, search repositories, read file contents, and manage organizations — all through the existing `api_call` tool.

## Problem

The agent had no way to interact with GitHub. The `gh` CLI requires interactive authentication that the agent cannot satisfy, and no GitHub integration preset existed in the integrations framework.

## Solution

A new `"github"` preset in `INTEGRATION_PRESETS` (`src/integrations.py`), following the same pattern as the existing Gitea preset:

- **Auth:** `header` with `Authorization: token YOUR_TOKEN`
- **Base URL:** `https://api.github.com`
- **Token:** GitHub Personal Access Token (classic) with `repo` scope — created at `https://github.com/settings/tokens`

### Files changed

| File | Change |
|------|--------|
| `src/integrations.py` | Added `github` preset with endpoint documentation |
| `routes/auth_routes.py` | Added `/user` health-check path; test returns authenticated user's login name |
| `static/js/settings.js` | Added GitHub icon to preset logo map |

### User flow

1. Settings → Integrations → Add Integration → select "API Service"
2. Select "GitHub" from the preset dropdown (auto-fills name, auth, and endpoint docs)
3. Paste a GitHub Personal Access Token
4. Save → Test → confirms "Authenticated as GitHub user '<login>'"

### Agent experience

Once configured, the integration's endpoints are injected into the agent's system prompt via `get_integrations_prompt()`. The agent uses the `api_call` tool with `integration: "github"` to:

- `GET /user/repos` — list repositories
- `POST /repos/{owner}/{repo}/issues` — create issues
- `GET /repos/{owner}/{repo}/pulls` — list pull requests
- `GET /search/repositories` — search repos
- `GET /repos/{owner}/{repo}/contents/{filepath}` — read files

## Testing checklist

- [ ] Server restarted after code changes
- [ ] `GET /api/auth/integrations/presets` returns the `github` preset
- [ ] Settings UI → Integrations → Add → API Service → "GitHub" appears in preset dropdown
- [ ] Selecting "GitHub" auto-fills name, auth type, auth header, and description
- [ ] Save + Test with a valid token returns "Authenticated as GitHub user '<login>'"
- [ ] Save + Test with an invalid token returns an error message
- [ ] Agent system prompt includes GitHub endpoints after configuration

## Screenshots

_(To be captured after filing)_

## Notes

- No new routes, tool schemas, or database tables — rides entirely on the existing integrations framework
- Token stored encrypted at rest via Fernet (same as all other integrations)
- Follows the exact same pattern as the existing `gitea` preset
