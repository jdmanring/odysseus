# Upstream Issue Draft: feat-gh-cli-detection

**File on:** `odysseus-dev/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/feat-gh-cli-detection.md`
**Branch:** `feat/gh-cli-detection`
**Type:** Enhancement

---

## Title

`[Agent] Surface gh CLI in system prompt when installed and authenticated`

---

## Body

**Area:** Agent context / Integrations

**Problem:**

When `gh` (GitHub CLI) is installed and authenticated on the host, the agent has no
way to know this. Users asking the agent to interact with GitHub receive broken or
unhelpful responses because the agent doesn't know it can run `gh` commands through
the `bash` tool.

Additionally, on Linux systems where `gh` authenticates via the system keyring,
Odysseus's bash tool subprocesses run without a D-Bus session and cannot read the
keyring — so even when `gh` is authenticated, running `gh` from within an agent
bash call fails with "requires authentication."

**Fix:**

1. Detect `gh` auth at prompt-build time via `gh auth status --hostname github.com`
   and inject a `## GitHub CLI` context block into the agent system prompt, listing
   common commands and instructing the agent to use `bash` + `gh` for all GitHub tasks.

2. When `gh` is authenticated via keyring, extract the token with `gh auth token` and
   set `GH_TOKEN` in the server process environment so that all subprocess calls
   (including the bash tool) inherit it without needing keyring access.

Both functions are silent no-ops when `gh` is absent or unauthenticated — no behaviour
change on hosts without `gh`.
