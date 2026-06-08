# [UPSTREAM] AGENTS.md — AI Agent Entry Point

## Status
- Issue filed: Not yet filed
- PR opened: Not yet opened
- Fix in fork: `feat/ai-documentation-system` branch / commit `97700f3` (updated `a1e3d85`)

## Notes

This is a **documentation addition**. Use the **Feature Request** template.

`AGENTS.md` is a file convention recognized by AI coding agents (Claude Code, Codex,
Cursor, Devin, OpenHands) as the primary entry point for understanding a project.
When an AI agent opens a repo it hasn't seen before, it looks for this file first.

The upstream-candidate content is the top portion of our fork's `AGENTS.md` — everything
above the "Fork-Specific Rules" section. The fork-specific rules (upstream remote, pipeline,
integration branch) are meaningless in the source project and must not be included.

**Scope of the upstream PR:**
- One new file: `AGENTS.md` at the repo root
- No other files changed

**No screenshots required** — documentation-only change.

---

## Staged Issue
<!-- James: open https://github.com/pewdiepie-archdaemon/odysseus/issues/new?template=feature_request.yml -->

**Prerequisites**
- [x] I searched open issues and this has not already been proposed.
- [x] I searched discussions and this is not already being debated there.
- [x] This is a concrete, actionable proposal — not a vague "it would be nice if..." request.

**Area:** Developer Experience / Documentation

**Problem or Motivation**

AI coding agents (Claude Code, GitHub Copilot/Codex, Cursor, Devin, OpenHands) have
adopted a convention of looking for `AGENTS.md` at the repo root as their first read
when entering an unfamiliar project. Without it, each agent session begins by
re-deriving the same basic facts: what the app is, how to run it, what the contribution
rules are, and what not to do. This costs tokens and produces inconsistent results
across sessions and across different agents.

Odysseus already documents these rules well in `CONTRIBUTING.md` and `README.md`, but
neither file is structured as an agent entry point — they are written for humans
browsing GitHub. An agent reading `CONTRIBUTING.md` cold has to parse a long document
to extract the handful of rules that directly affect its behavior.

**Proposed Solution**

Add `AGENTS.md` at the repo root. The file serves as a fast-path summary for AI agents:
what the project is, what the key rules are (issue-before-PR, no sudo, verify in the
running app, screenshots for visual changes), and where to go for more detail.

Content is drawn directly from `CONTRIBUTING.md` — nothing new is introduced, just
surfaced in the format agents expect.

```markdown
# Odysseus — AI Agent Instructions

Odysseus is a self-hosted AI workspace: FastAPI backend, plain-JS frontend, SQLite +
ChromaDB storage. Runs locally at `127.0.0.1:8000`. Read `CONTRIBUTING.md` for the
full contribution rules. Key points for AI agents are summarized below.

---

## Rules

**Read the source before writing code.** Find the relevant file, read it, report what
you find. Do not generate code against an assumption about what the code looks like.

**No sudo.** If an operation requires elevated privileges, write the command for the
user to run — do not execute it yourself.

**Issue before PR.** Upstream explicitly requires an issue to exist before any PR is
filed. This applies to agent-generated work as much as human work — see `CONTRIBUTING.md`
for the full policy on agent PRs.

**One thing per PR.** No mixing unrelated fixes, formatting changes, or refactors into
a single PR. Each PR must be reviewable in isolation.

**Verify the fix in the running app.** Tests are not sufficient. Before any PR is
considered ready, the fix must be confirmed end-to-end in the actual application.

**Visual changes require screenshots.** Any PR touching `static/js/`, HTML, or CSS
must include a screenshot or clip. See `CONTRIBUTING.md` for details.

**Use existing constants and helpers.** Never hardcode paths, ports, or URLs that the
project already exposes. See `CONTRIBUTING.md` — Code conventions.

## Working Style

- State what you are about to do before making non-trivial changes.
- Keep responses concise. No trailing summaries restating what the diff already shows.
- No speculative files — don't create planning docs, analysis notes, or scaffolding
  unless explicitly asked.
```

**Alternatives Considered**

Relying on `CONTRIBUTING.md` alone: agents do read it, but it is structured for human
contributors and requires parsing to extract agent-relevant rules. `AGENTS.md` is a
zero-ambiguity shortcut that agents are already trained to look for.

Adding agent instructions to `README.md`: README is user-facing. Mixing developer/agent
workflow instructions into it makes the README harder to read for both audiences.

---

## Staged PR
<!-- James: fill in Fixes #NNN, then copy into the GitHub PR form -->

**Title:** `docs: add AGENTS.md — AI agent entry point`

**Branch:** `jdmanring/odysseus:upstream/agents-md` (build from `upstream-mirror`, single file add)

**Description:**

Adds `AGENTS.md` at the repo root — the conventional entry point for AI coding agents
(Claude Code, Codex, Cursor, Devin, OpenHands).

The file summarizes the contribution rules that most directly affect agent behavior:
read source before coding, issue before PR, one thing per PR, verify in the running
app, screenshots for visual changes, use existing constants. All content is drawn
directly from `CONTRIBUTING.md` — nothing new, just surfaced in the format agents
expect.

Fixes #NNN

**How to Test**

1. Clone the repo fresh in a Claude Code / Cursor / Copilot session.
2. Confirm the agent opens `AGENTS.md` as its first read (or responds correctly when
   asked "what are the rules here?").
3. Confirm no existing behavior changes — this is a new file only.

**Checklist**
- [x] This PR targets `dev`, not `main`
- [x] This PR is focused — one file added, no unrelated changes
- [x] I searched existing issues and PRs — not a duplicate
- [x] Documentation-only change — no app behavior modified, no screenshot required
