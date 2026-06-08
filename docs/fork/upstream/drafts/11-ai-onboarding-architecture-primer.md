# [UPSTREAM] AI_ONBOARDING.md — Architecture Primer for AI Contributors

## Status
- Issue filed: Not yet filed
- PR opened: Not yet opened
- Fix in fork: `feat/ai-documentation-system` branch

## Notes

This is a **documentation addition**. Use the **Feature Request** template.

**Upstream scope** — contribute a trimmed `AI_ONBOARDING.md` at the repo root containing
only content that applies to the upstream source project. Strip before filing:

- Remove the "Fork Additions" section entirely (Qt wrapper, aria2c tooling, etc. are
  not in upstream yet — those will arrive with their own PRs)
- Remove "Where to Go Next" table rows that reference fork-specific docs
- Update the header note to not reference `AGENTS.md` until/unless that PR merges first;
  if #10 (AGENTS.md) merges first, the header can reference it

File this PR **after** `AGENTS.md` (#10) merges upstream, since AGENTS.md points here.

**No screenshots required** — documentation only.

---

## What Goes Upstream (stripped content)

The upstream-appropriate sections are:

1. **What It Is** — description of Odysseus (no Qt wrapper mention)
2. **How a Chat Request Flows** — request flow diagrams (backend + agent mode)
3. **Code Layout** — backend and frontend file map (excluding fork-added files)
4. **Data Storage** — SQLite, ChromaDB, settings.json override behavior
5. **The Cookbook** — download pipeline, aria2c progress format, `_dlFileTracker`
   (only after aria2c PR #08 merges upstream)
6. **Things That Will Bite You** — sharp edges that apply to the upstream codebase:
   - No bundler / new JS files need a script tag
   - `QWebEngineView` compat note (only after Qt PR #09 merges)
   - `_dlFileTracker` (only after aria2c PR #08 merges)
   - HF signed URLs expire (after #08)
   - `data/settings.json` overrides `src/settings.py`
   - Agent tool budget default

**Do not include upstream:**
- "Fork Additions" section
- Qt wrapper file references (linux_wrapper.py, qt-bridge.js, platform.js) until #09 merges
- aria2c tooling references (aria2c_download.py, bin_manager.py) until #08 merges
- "Where to Go Next" links to docs/fork/ — fork-specific paths

**Filing order dependency:**
The cleanest upstream `AI_ONBOARDING.md` is a moving target — its content expands as
our other PRs merge. Recommended filing order:
1. #10 AGENTS.md (ready now — no dependencies)
2. Simple bug fixes (#02–#07)
3. #08 aria2c backend (then AI_ONBOARDING.md Cookbook section is accurate)
4. #11 AI_ONBOARDING.md (after #10 and #08 have merged)
5. #09 Qt wrapper (large, independent)

---

## Staged Issue
<!-- James: open https://github.com/pewdiepie-archdaemon/odysseus/issues/new?template=feature_request.yml -->

**Prerequisites**
- [x] I searched open issues and this has not already been proposed.
- [x] I searched discussions and this is not already being debated there.
- [x] This is a concrete, actionable proposal — not a vague "it would be nice if..." request.

**Area:** Developer Experience / Documentation

**Problem or Motivation**

AI coding agents (Claude Code, Codex, Cursor, Devin, OpenHands) entering the Odysseus
codebase cold must re-derive the same architectural facts every session: where the
request flow starts, what drives the Cookbook downloads, why adding a JS file requires
a `<script>` tag, how `data/settings.json` relates to `src/settings.py`. This takes
tokens and produces inconsistent results.

`AGENTS.md` (see companion PR) gives agents the rules. `AI_ONBOARDING.md` gives them
the mental model — the architectural facts that take the longest to re-derive.

**Proposed Solution**

Add `AI_ONBOARDING.md` at the repo root. Content:

- One-paragraph description of what Odysseus is
- Chat request flow (user → chat.js → POST /api/chat_stream → llm_core.py → SSE → renderer)
- Agent mode flow (agent_loop.py, tool calls, result injection)
- Backend directory map (routes/, src/, core/, mcp_servers/)
- Frontend structure (no bundler, plain ES modules, new files need script tags)
- Data storage (SQLite, ChromaDB, settings.json override behavior)
- Cookbook download pipeline (cookbookDownload.js → cookbook_routes.py → aria2c subprocess → poll loop)
- Sharp edges that take time to discover:
  - No bundler — new JS files need a `<script>` tag in index.html
  - Model picker autohides after 10 non-whitespace characters
  - Plan Window only updates when `update_plan` is called
  - `data/settings.json` wins over `DEFAULT_SETTINGS` in `src/settings.py`

**Alternatives Considered**

Embedding this in `CONTRIBUTING.md`: CONTRIBUTING is about process, not architecture.
Mixing them makes both harder to read.

Relying on README.md: README is user-facing. It describes what the app does, not how
it's built internally.

---

## Staged PR
<!-- James: fill in Fixes #NNN once issue is filed, then copy into GitHub PR form -->
<!-- File this after AGENTS.md has merged upstream -->

**Title:** `docs: add AI_ONBOARDING.md — architecture primer for AI agents and new contributors`

**Branch:** `jdmanring/odysseus:upstream/ai-onboarding` (build from `upstream-mirror`, single file add)

**Description:**

Adds `AI_ONBOARDING.md` at the repo root — a concise architecture primer designed to
give AI coding agents (and new human contributors) an accurate mental model without
reading the entire codebase.

Companion to `AGENTS.md` (rules) — this file covers the facts: what Odysseus is,
how a request flows, what drives the Cookbook, and the sharp edges that take the most
time to discover from code alone.

All content is derived by reading the existing source — nothing is invented. The file
will expand naturally as more features (aria2c, Qt wrapper) are contributed upstream
through their own PRs.

Fixes #NNN

**How to Test**

1. Open the repo in a Claude Code / Cursor / Copilot session.
2. Ask the agent "how does a chat request flow through this codebase?" — it should
   answer accurately from `AI_ONBOARDING.md` without reading multiple source files.
3. Verify no app behavior changes — documentation only.

**Checklist**
- [x] This PR targets `dev`, not `main`
- [x] This PR is focused — one file added, no unrelated changes
- [x] I searched existing issues and PRs — not a duplicate
- [x] Documentation-only change — no screenshot required
