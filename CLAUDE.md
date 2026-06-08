# Odysseus Fork — Claude Code Instructions

Read `AI_CONTEXT.md` for the code mental model and fork context.
Full hard rules: `AI_RULES.md`. Active work: `docs/fork/active-work.md`.
Branch and pipeline rules: `docs/dev/git-branch-workflow.md` — read before touching any branch.

---

## Hard Rules (non-negotiable)

**No sudo.** Write `! sudo <command>` for James to run. Never execute elevated commands yourself.

**Read before coding.** For any non-trivial change: read the relevant source, report what you found, then wait for direction before modifying. Don't start editing because you think you know what needs to change.

**Never push to `upstream` remote.** The `upstream` remote is `pewdiepie-archdaemon/odysseus` — read-only. Never push there under any circumstances.

**Never commit to `upstream-mirror`.** This branch is reset-only. Any commits made to it will be destroyed on the next sync. Treat it as read-only.

**Never cherry-pick upstream → `develop` directly.** Upstream changes come in through the ingest pipeline only: `upstream/dev` → `upstream-mirror` → `integration` → `develop`. This preserves gate verification and a clean merge history. See `docs/dev/git-branch-workflow.md` for the pipeline procedure.

**Never file upstream issues or PRs.** Agents stage work; James files. Do not open issues or PRs on `pewdiepie-archdaemon/odysseus` without James's explicit per-action authorization. Upstream's CONTRIBUTING.md prohibits agent-filed PRs.

**Issue first, branch second.** No branch exists without a corresponding issue on `jdmanring/odysseus`. Create the issue before creating any branch.

**Never close issues without verification.** An issue is closed only when the fix is confirmed working — not when you believe you've applied a fix. Incorrect closings disrupt workflow tracking and will not be tolerated.

---

## Branch Origin Rules (critical — easy to get wrong)

There are two kinds of work branches and they have different origins:

| Work type | Branch origin | Merge destination |
|-----------|--------------|-------------------|
| **Upstream-candidate** (fixes/features to share upstream) | `upstream-mirror` | cherry-pick to `develop`; branch stays for upstream PR |
| **Fork-only** (Qt wrapper, pipeline, docs, fork-specific) | `develop` | merge to `develop`; close issue |

Getting this wrong contaminates upstream-candidate branches with fork-specific history and makes them unusable as PRs.

---

## Concise Responses

- No trailing summaries after edits ("Here's what I changed: ...")
- No re-explaining what was just read
- State intent before non-trivial tool use; otherwise act
- One-sentence updates at key moments while working
