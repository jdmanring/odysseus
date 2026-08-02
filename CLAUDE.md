# Odysseus Fork: Claude Code Instructions

Read `docs/ai/CONTEXT.md` for the code mental model and fork context.
Fork workbench policy (hard rules, pipeline procedures): `docs/fork/ai-policy.md`.
Upstream contribution standards: `docs/ai/RULES.md`. Active work: `docs/fork/active-work.md`.
Branch and pipeline rules: `docs/dev/git-branch-workflow.md`; read before touching any branch.

---

## The Purpose of This Fork

**This fork is a contribution workbench, not a divergent product.**

It is used to develop fixes and features and stage them as upstream pull requests to `odysseus-dev/odysseus`. The fork is not meant to stay separate: everything that improves Odysseus should go upstream.

**The default classification for any fix, feature, or documentation is upstream-candidate.**

Fork-only is the narrow exception, reserved for the workshop tooling itself:
- `CLAUDE.md`: these instructions
- `docs/fork/`: fork management state (active-work, issue-tracker, pr-status, changes-from-upstream)
- `tooling/sync-upstreams/`: the sync pipeline
- `.github/workflows/sync-upstream.yml`: CI for the sync

Everything else defaults to upstream-candidate: bug fixes, features, `qt_wrapper.py`, the download stack, UI work, `docs/ai/CONTEXT.md`, `docs/ai/RULES.md`, `docs/dev/` documentation, architecture docs, user docs. If it makes Odysseus better, it belongs upstream.

**Use directory structure to determine classification, not explicit listing.** `docs/fork/` = fork management = fork-only. `docs/dev/` = development documentation = upstream-candidate. `docs/ai/` = AI onboarding content = upstream-candidate. When in doubt, ask: does this belong to the project, or does it belong to the workbench?

**Never classify something as fork-only without a specific reason it cannot go upstream.** "It touches fork-specific code" is not a reason; that code is usually itself upstream-candidate. When in doubt, assume upstream-candidate.

---

## Hard Rules (non-negotiable)

**No sudo.** Write `! sudo <command>` for the user to run. Never execute elevated commands yourself.

**Read before coding.** For any non-trivial change: read the relevant source, report what you found, then wait for direction before modifying. Don't start editing because you think you know what needs to change.

**Never push to `upstream` remote.** The `upstream` remote is `odysseus-dev/odysseus`, and it is read-only. Never push there under any circumstances.

**Never commit to `upstream-mirror`.** This branch is reset-only. Any commits made to it will be destroyed on the next sync. Treat it as read-only.

**Never cherry-pick upstream -> `develop` directly.** Upstream changes come in through the ingest pipeline only: `upstream/dev` -> `upstream-mirror` -> `integration` -> `develop`. This preserves gate verification and a clean merge history. See `docs/dev/git-branch-workflow.md` for the pipeline procedure.

**Never file upstream issues or PRs.** Agents stage work; the human author files. Do not open issues or PRs on `odysseus-dev/odysseus` without explicit per-action authorization. Upstream's CONTRIBUTING.md prohibits agent-filed PRs.

**Issue first, branch second.** No branch exists without a corresponding entry in the **local** tracker, `docs/fork/issues/` (source of truth: `issue-export.json`; `INDEX.md` is the committed index; regenerate with `python3 tooling/issues_to_markdown.py`). Create the entry before creating any branch. The workbench repo has GitHub Issues **disabled by design**: it stages upstream PRs and is not a public contribution target. Historical docs cite `#N` against the retired `jdmanring/odysseus`; those numbers resolve in the local index.

**Never close issues without verification.** An issue is closed only when the fix is confirmed working, not when you believe you've applied a fix. What "confirmed working" means depends on type: fork-only issues close when the fix lands on `develop`; upstream-candidate issues stay open until the upstream PR is filed (the filed PR is the only active tracker until then). Incorrect closings disrupt workflow tracking and will not be tolerated.

**Never write a person's name into a document.** Instructions and workflows apply to whoever is following them. Use second person ("you file", "open the PR") or imperative ("file the issue", "create a branch"), never "James files" or "James creates". URLs containing `jdmanring` (GitHub links, AUR package names, branch references) are factual resource identifiers and are correct; this rule applies to prose instructions only.

---

## Branch Origin Rules (critical; easy to get wrong)

There are two kinds of work branches and they have different origins:

| Work type | Branch origin | Merge destination |
|-----------|--------------|-------------------|
| **Upstream-candidate** (default; almost everything) | `upstream-mirror` | cherry-pick to `develop`; branch stays for upstream PR |
| **Fork-only** (sync pipeline, fork management docs, fork CI) | `develop` | merge to `develop`; close issue when fix is verified on develop |

Getting this wrong contaminates upstream-candidate branches with fork-specific history and makes them unusable as PRs.

**If you are unsure which category a piece of work belongs to, it is upstream-candidate.** The fork-only category is small and well-defined. See the Fork Purpose section above.

---

## Concise Responses

- No trailing summaries after edits ("Here's what I changed: ...")
- No re-explaining what was just read
- State intent before non-trivial tool use; otherwise act
- One-sentence updates at key moments while working
