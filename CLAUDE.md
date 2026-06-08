# Odysseus Fork — Claude Code Instructions

Read `AI_ONBOARDING.md` first. It gives you the code mental model, architecture, and
what's fork-specific. For active work and branch status: `docs/fork/active-work.md`.

---

## Hard Rules

- **No sudo.** Write `! sudo <command>` for James to run. Never execute elevated commands directly.
- **Verify before coding.** Read the relevant source first. Report findings, then wait for direction.
- **Report before implementing** non-trivial changes. James confirms direction first.
- **Never push to `upstream` remote, file issues, or open PRs upstream** without James's
  explicit per-action authorization. Stage contribution drafts in `docs/fork/upstream/drafts/`.
- **Never commit to `upstream-mirror` branch.** This branch is reset-only; commits are lost.
- **Never cherry-pick upstream → `develop` directly.** Use the pipeline:
  `docs/fork/upstream/how-to-contribute.md`.

---

## Working Style

- Concise responses. No trailing summaries after diffs.
- State intent before non-trivial changes.
- No unnecessary files — don't create planning or analysis docs unless asked.
- No sudo, ever.
