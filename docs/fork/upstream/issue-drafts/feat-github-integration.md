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

**Problem:**

1. When `gh` (GitHub CLI) is installed and authenticated on the host, the agent has no
   way to know this. Users asking the agent to interact with GitHub get broken responses
   because the agent doesn't know it can just run `gh` commands through `bash`.

2. The `api_call` tool (for Miniflux, Home Assistant, Linkding, etc.) is absent from
   the RAG embedding index, so the tool retrieval system never surfaces it when users
   ask about their configured services. Models also sometimes emit the wrong parameter
   key (`integration_name`, `id`, etc.) instead of `integration`, causing every call
   to fail with `No integration matching ''`.

3. Two Settings UI bugs affect all presets: selecting a preset with a `base_url` does
   not auto-fill the Base URL field, and reopening a saved integration resets the preset
   dropdown to "Custom (no preset)".

**Fix:**

- Detect `gh` auth at prompt-build time and inject a GitHub CLI context block so the
  agent uses `bash` + `gh` for GitHub operations automatically.
- Add `api_call` to the embedding index and keyword hints so it's retrievable.
- Accept common parameter key aliases in `do_api_call`.
- Fix the two Settings preset UI bugs.
