# Odysseus Fork — AI Agent Instructions

Read `AI_ONBOARDING.md` next. It gives you the complete code mental model, request
flow, file map, fork additions, and where every doc lives. Hard rules are below.

---

## Hard Rules

- **No sudo.** Write `! sudo <command>` for James to run. Never execute elevated commands directly.
- **Verify before coding.** Read the relevant source first. Report findings, then wait for direction on non-trivial changes.
- **Never push to `upstream` remote, file issues, or open PRs upstream** without James's
  explicit per-action authorization. Upstream's own CONTRIBUTING.md explicitly prohibits
  agent-filed PRs. Stage contribution drafts in `docs/fork/contributions/upstream/`.
- **Never commit to `upstream-mirror` branch.** This branch is reset-only; commits are lost.
- **Never cherry-pick upstream → `develop` directly.** Use the pipeline:
  `docs/fork/upstream/how-to-contribute.md`.

## Working Style

- Concise responses. No trailing summaries after diffs.
- State intent before non-trivial changes.
- No unnecessary files — don't create planning or analysis docs unless asked.
