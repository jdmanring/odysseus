# Documentation Restructure Plan

## Problem

The project documentation had accumulated into an unmaintainable state:
- 8 exact duplicate files in `docs/` root vs. organized subdirectories
- No `CLAUDE.md`: Claude Code reads this automatically but it didn't exist
- `docs/fork/` was a grab-bag: build instructions, issue tracking, contribution workflow, and governance mixed together
- Multiple single-file directories (`docs/ai/`, `docs/tech/`, `docs/architecture/`, `docs/lessons_learned/`)
- File names with underscores, ALLCAPS, and opaque abbreviations that require context to decode

## Goal

A documentation system where an AI landing cold on this repo instantly knows where
everything is and what it means: without memory instructions, without being told.

---

## New Structure

```
/
  CLAUDE.md                         ← auto-loaded by Claude Code: hard rules + entry point
  AI_ONBOARDING.md                  ← primer: mental model, code map, fork additions, sharp edges

docs/
  project/                          ← understanding the codebase
    architecture.md
    non-obvious-behaviors.md
    ai-capabilities-reference.md

  fork/                             ← fork management hub
    README.md                       ← what this fork is, relationship to upstream
    changes-from-upstream.md        ← master divergence record
    active-work.md                  ← in-progress items
    issue-tracker.md                ← bugs and open issues
    fork-changelog.md
    linux-build-and-install.md
    linux-service-lifecycle.md
    aur-package.md

    upstream/                       ← contributing back to upstream
      how-to-contribute.md
      pr-status.md
      bug-discoveries.md
      drafts/                       ← per-PR staged docs

    fork-only/                      ← work staying in this fork

  dev/                              ← developer workflow
    local-setup-and-running.md
    git-branch-workflow.md
    testing-standards.md
    lessons-learned.md
    agent-operating-guide.md
    documentation-templates.md

  user/                             ← user-facing understanding
    interface-map.md
    user-workflows.md
    cookbook-lifecycle.md
    plan-sync-guide.md
    ux-tips.md

  audit/                            ← health snapshots
    baseline-summary.md
    feature-coverage-matrix.md
    ux-friction-points.md
    pr-blocker-audit.md
    priority-matrix.md

  archive/
```

---

## What Changed

### New files
- `CLAUDE.md`: repo root, auto-loaded by Claude Code
- `docs/fork/README.md`: fork orientation
- `docs/fork/changes-from-upstream.md`: master divergence record
- `docs/fork/active-work.md`: in-progress work
- `docs/dev/local-setup-and-running.md`: extracted from AGENT_CONTEXT.md
- `docs/dev/git-branch-workflow.md`: extracted from AGENT_CONTEXT.md

### Deleted
- 8 exact duplicate files from `docs/` root
- `docs/index.md` (empty)
- `docs/fork/AGENT_CONTEXT.md` (replaced by CLAUDE.md + AI_ONBOARDING.md + distributed docs)
- `docs/fork/upstream-contributions.md` (content -> `docs/fork/upstream/bug-discoveries.md`)
- `docs/ai/update_plan_ops.md` (stale)
- All single-file directory wrappers merged into parent domains

### Renamed/moved (content unchanged)
See full mapping in the approved plan at `.claude/plans/snoopy-crunching-snail.md`.

---

## Why

- `CLAUDE.md` means hard rules load automatically without any memory system
- `docs/fork/` is now purely a fork management system: divergence tracking + upstream contribution workflow
- Every filename is self-explanatory from a directory listing alone
- No duplicate sources of truth
- AI can orient in one read of `AI_ONBOARDING.md` and navigate the rest by filename
