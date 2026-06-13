# Upstream Issue Draft: feat-github-integration

**File on:** `pewdiepie-archdaemon/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/feat-github-integration.md`
**Branch:** `feat/github-integration`
**Type:** Enhancement

---

## Title

`[Integrations] Add GitHub preset for agent API access`

---

## Body

**Area:** Integrations

**Problem / Motivation:**
The agent has no way to interact with the GitHub API. The `gh` CLI requires interactive terminal authentication that the agent cannot satisfy — it cannot respond to prompts. No GitHub integration preset exists in the integrations framework. Users who want the agent to create issues, read pull requests, search repositories, or read file contents from GitHub have no supported path to configure this.

**Proposed Solution:**
A `github` preset in `INTEGRATION_PRESETS` (`src/integrations.py`), following the same pattern as the existing Gitea preset:

- **Auth:** `Authorization: token YOUR_TOKEN` header
- **Base URL:** `https://api.github.com`
- **Token:** GitHub Personal Access Token (classic) with `repo` scope, created at `https://github.com/settings/tokens`

Once configured via Settings → Integrations, the integration's endpoints are injected into the agent's system prompt. The agent uses the existing `api_call` tool with `integration: "github"` to access standard REST API endpoints:

- `GET /user/repos` — list repositories
- `POST /repos/{owner}/{repo}/issues` — create issues
- `GET /repos/{owner}/{repo}/pulls` — list pull requests
- `GET /search/repositories` — search repos
- `GET /repos/{owner}/{repo}/contents/{filepath}` — read file contents
- `GET /orgs/{org}/members` — list org members

**Alternatives Considered:**
- `gh` CLI: requires interactive auth the agent cannot provide.
- Raw `curl` / HTTP calls via system prompt: works ad-hoc but requires per-user manual configuration and has no UI for token management or connection testing.
- A GitHub preset in the existing integrations framework is consistent with how Gitea is handled, gives users a tested-connection flow, and stores the token encrypted at rest via the same Fernet path as all other integrations.
