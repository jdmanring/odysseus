# Upstream Contribution Workflow

This document defines how contributions flow from this fork to `pewdiepie-archdaemon/odysseus`.
It is binding on all agents and must be followed exactly, every time, without exception.

---

## Two-Repo Model

| Remote | Repo | Purpose |
|--------|------|---------|
| `origin` | `jdmanring/odysseus` | James's fork — all active development |
| `upstream` | `pewdiepie-archdaemon/odysseus` | Source project — contributions target `dev` branch |

These are completely separate. Pushing to `origin` is routine. Sending anything to
`upstream` (issues, PRs, comments) requires James's explicit per-action authorization.

---

## Absolute Rules for Agents

**An agent NEVER files an issue or PR to upstream directly.**
Upstream's own CONTRIBUTING.md states:
> "If you are running an LLM agent (Devin, Cursor, OpenHands, Claude Code, etc.)
> against this repo: please open an issue describing the problem first instead of
> opening a PR directly. Bulk agent-generated PRs that don't match the project's
> visual style or contribution format will be closed without review, even when the
> underlying fix is correct."

Agent responsibilities:
- Maintain the staged docs in `docs/fork/upstream/drafts/`
- Keep each staged doc current and copy-paste ready
- **Never run `gh issue create`, `gh pr create`, or any equivalent targeting `upstream`**
- Inform James when a contribution is ready to file and what to do

James's responsibilities:
- Review staged docs before filing
- File the issue on GitHub personally
- Add the issue number to the staged PR section
- File the PR personally after verifying the fix in the running app

---

## Step-by-Step Workflow

### 1. Develop and confirm the fix in the fork

All work happens on a feature or fix branch off `develop`:
```
git checkout develop
git checkout -b fix/short-description
```
The fix is merged to `develop` through normal fork development. This has nothing to do
with upstream contribution — the fork always gets the fix regardless.

### 2. Stage the contribution doc

Each upstream contribution lives in `docs/fork/upstream/drafts/NN-name.md`.
The document has two sections that exactly mirror upstream's GitHub templates:

- **Staged Issue** — matches `bug_report.yml` or `feature_request.yml`
- **Staged PR** — matches `pull_request_template.md`

These sections are written to be copy-pasted directly into GitHub. Nothing should need
rewriting at filing time except filling in the issue number.

### 3. James files the issue on GitHub

James opens `pewdiepie-archdaemon/odysseus/issues/new`, selects the correct template,
pastes the staged issue content, and submits. The issue number is recorded in the
staged doc's Status section.

### 4. Prepare the upstream PR branch

The PR branch is built from `upstream-mirror`, not from `develop`. Fork-specific
changes (wrapper, tooling paths, KDE integration, etc.) must never appear in an
upstream PR.

```bash
git checkout upstream-mirror
git checkout -b upstream/fix-short-description
# Apply only the minimal upstream-relevant diff
git push origin upstream/fix-short-description
```

### 5. James runs the app and verifies

Before filing the PR, James must run the actual app and verify the fix end-to-end.
Unit tests alone are not sufficient — upstream's CONTRIBUTING.md is explicit about this.
For any visual change, a screenshot or clip is required.

### 6. James files the PR on GitHub

James opens a PR from `jdmanring/odysseus:upstream/fix-short-description`
against `pewdiepie-archdaemon/odysseus:dev`, pastes the staged PR content,
fills in `Fixes #NNN` with the real issue number, attaches screenshots if required,
and submits.

---

## Upstream's Branch Model

Upstream has two branches:

| Branch | Purpose |
|--------|---------|
| `dev` | All PRs land here — default base for contributions |
| `main` | Curated stable release — never target this |

**All PRs must target `dev`.** The PR template has a checkbox for this.

---

## Upstream's PR Requirements Checklist

Before marking a contribution as ready to file, verify all of the following:

- [ ] A GitHub issue exists for this fix/feature
- [ ] PR targets `dev`, not `main`
- [ ] PR is focused — one bug or feature only, no unrelated cleanup mixed in
- [ ] Searched existing issues and PRs — not a duplicate
- [ ] App was run locally and fix verified end-to-end (not just tests)
- [ ] **If any `static/js/` or HTML/CSS was touched:** screenshot or clip attached
- [ ] Change uses existing CSS variables — no new colors, font sizes, or spacing units
- [ ] No Unicode emoji in UI or code
- [ ] No parallel components invented — existing widgets extended instead
- [ ] How-to-Test section is complete with step-by-step instructions
- [ ] PR description is a real summary (not "fixed bug" or "added feature")

---

## Contribution Doc Format

Each `docs/fork/upstream/drafts/NN-name.md` follows this template:

```
# [UPSTREAM] Title

## Status
- Issue filed: #NNN (link) / Not yet filed
- PR opened: (link) / Not yet opened
- Fix in fork: develop branch / commit hash

## Notes
Any context specific to this contribution that isn't in the templates.
LLM agent: read this section before doing anything.

---

## Staged Issue
<!-- James: copy everything below this comment into GitHub Issues → correct template -->

### (Bug Report or Feature Request content here — matches upstream template exactly)

---

## Staged PR
<!-- James: fill in the issue number, then copy everything below into the GitHub PR form -->

### (PR template content here — matches upstream pull_request_template.md exactly)
```

---

## Index of Staged Contributions

See `docs/fork/upstream/pr-status.md` — that file is the authoritative index and is
kept current. The drafts themselves are in `docs/fork/upstream/drafts/`.
