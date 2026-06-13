# Upstream Issue Draft: feat-github-integration

**File on:** `pewdiepie-archdaemon/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/feat-github-integration.md`
**Branch:** `feat/github-integration`
**Type:** Enhancement / Bug fix

---

## Title

`[Agent] Surface gh CLI in system prompt when installed; fix api_call discoverability`

---

## Body

**Area:** Agent context / Integrations

**Problem / Motivation:**

When `gh` (GitHub CLI) is installed and authenticated on the host, the agent has no way
to know this. Users asking the agent to interact with GitHub — list repos, create issues,
read pull requests, read file contents — get broken or confused responses because the
agent doesn't know it can just run `gh` commands via `bash`.

Separately, the `api_call` tool (used for Miniflux, Home Assistant, Linkding, etc.) is
missing from the RAG embedding index, so the tool retrieval system never surfaces it when
users ask about their configured external services. The tool also only accepts the exact
key `"integration"` for the integration name, but models sometimes emit `"integration_name"`,
`"integration_id"`, `"name"`, or `"id"`, causing every call to fail with
`No integration matching ''`.

Two Settings UI bugs also affect all presets: selecting a preset with a `base_url` does not
auto-fill the Base URL field, and reopening a saved integration resets the preset dropdown
to "Custom (no preset)".

**Proposed Solution:**

1. `get_github_cli_prompt()` in `src/integrations.py`: runs `gh auth status` at
   prompt-build time (5 s timeout, silently skipped if `gh` is absent or unauthenticated).
   When authenticated, injects a `## GitHub CLI` block into the agent system prompt
   listing common `gh` commands. The agent then reaches for `bash` + `gh` naturally.

2. `src/agent_loop.py`: calls `get_github_cli_prompt()` and appends the result
   alongside the integrations context block.

3. `src/tool_index.py`: adds `api_call` to `BUILTIN_TOOL_DESCRIPTIONS` so the
   embedding index can retrieve it; adds integration-related keyword hints
   (`github`, `miniflux`, `rss`, `home assistant`, `feed`, `bookmark`, etc.) to
   `_KEYWORD_HINTS`.

4. `src/tool_implementations.py`: `do_api_call` accepts `integration_name`,
   `integration_id`, `name`, `id` as aliases; falls back to the only configured
   integration when the field is empty and exactly one is configured.

5. `static/js/settings.js`: `_applyPreset` sets `url.value = p.base_url` when the
   preset defines one; edit form restores `preset.value` from the saved item on reopen.

**Why `gh` and not the REST API directly?**
`gh` is already authenticated via the system credential store — no token management
needed. It handles pagination, rate limiting, and auth transparently. For users who
don't have `gh`, the integrations framework with a PAT token remains the fallback
(supported by the `api_call` discoverability fixes in this same PR).
