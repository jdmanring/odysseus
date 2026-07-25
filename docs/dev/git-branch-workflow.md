# Git Branch Workflow

This document is the authoritative reference for branching, the upstream ingest pipeline,
and the full issue-to-upstream-PR lifecycle. Read it completely before touching any branch.

---

## Branch Map

| Branch | Purpose | Rules |
|--------|---------|-------|
| `upstream-mirror` | Exact copy of `upstream/dev`, reset on every sync | **Never commit here.** Read-only staging surface. |
| `integration` | Vetted upstream changes that passed all pipeline gates | Only the pipeline writes here. Never commit directly. |
| `develop` | Active fork development; primary working branch | All fork work lands here eventually. |
| `main` | Stable fork releases | Merge from `develop` when releasing. |
| `feat/*` / `fix/*` | Feature and fix work branches | See origin rules below; origin depends on work type. |
| `refactor/*` | Refactor branches | Same origin rules apply. |
| `sync/staging-*` | Temporary pipeline staging branches | Created and deleted automatically by the pipeline. |

**Upstream remote branches** (`upstream/dev`, `upstream/main`) are read-only fetch targets. Never push to them.

---

## Two Kinds of Work Branches, Different Origins

This is the most important thing to get right. There are two categories of work and they require different branch origins.

**The default is upstream-candidate.** Fork-only is the narrow exception: only the sync
pipeline (`tooling/sync-upstreams/`), fork CI (`.github/workflows/sync-upstream.yml`),
and fork management docs (`docs/fork/`). Everything else defaults to upstream-candidate,
including new files, large features, and documentation.

### Category 1: Upstream-Candidate (the default; almost all work)

These branches are staging for upstream pull requests. They must:
- Contain **only the changes for that one fix or feature**, nothing from the fork-only list above
- Start from `upstream-mirror` so they have no fork history
- Have a **single clean commit** (or a small number of tightly related commits)

```bash
# Always fetch first to ensure upstream-mirror is current
git fetch origin upstream-mirror

# Create the branch from upstream-mirror
git checkout -b fix/short-description origin/upstream-mirror

# Do the work — only the files relevant to this specific fix
# Then commit as one clean commit
git add <specific files only>
git commit -m "fix: clear description of what this fixes"

# Cherry-pick to develop so the fix is also in our working branch
git checkout develop
git cherry-pick <commit-hash>
git checkout fix/short-description   # branch stays — it's the upstream PR staging
```

The branch itself is kept permanently as the upstream PR staging. Do not delete it after cherry-picking to develop.

### Category 2: Fork-Only (sync pipeline, fork CI, fork management docs; nothing else)

These branches will never go upstream. They branch from `develop` and merge back.
If you are unsure whether something belongs here, it belongs in Category 1.

```bash
git checkout develop
git checkout -b feat/short-description

# Do the work
git add <files>
git commit -m "feat: description"

# When complete, merge to develop and close the issue
git checkout develop
git merge feat/short-description
# Optionally delete the branch after merge (fork-only branches don't need to persist)
```

---

## Remotes

```
origin    → git@github.com:<you>/odysseus.git                (your fork — normal dev target)
upstream  → git@github.com:odysseus-dev/odysseus.git  (source — NEVER push here)
```

---

## Issue-First Workflow

Every piece of work starts with a GitHub issue. No exceptions.

```
1. Create issue on your fork's GitHub
   - Bug: include Install Method, OS, numbered Steps to Reproduce, Expected/Actual Behaviour
   - Enhancement: include Area, Problem or Motivation, Proposed Solution, "willing to implement?"

2. Determine work category:
   - Upstream-candidate → branch from upstream-mirror (see Category 1 above)
   - Fork-only          → branch from develop (see Category 2 above)

3. Do the work; commit cleanly

4. Merge/cherry-pick to develop

5. If upstream-candidate:
   - Branch stays at single clean commit, ready to file a PR
   - Update docs/fork/upstream/pr-status.md with status (Ready to file / Needs X)
   - Open the PR: `<your-fork>:<branch>` → `odysseus-dev/odysseus:dev`
   - Add upstream issue # to pr-status.md after the issue is created

6. Close the fork issue when the fix is confirmed working
```

The current issue list and branch map is in `docs/fork/issue-tracker.md`.
Upstream PR readiness status is in `docs/fork/upstream/pr-status.md`.

---

## Upstream Ingest Pipeline

Upstream changes flow into this fork through a verified pipeline. **Never bypass it.**

```
upstream/dev
    ↓  (git fetch + reset)
upstream-mirror
    ↓  (merge into temp staging branch off integration)
sync/staging-TIMESTAMP
    ↓  Gate 1: Python syntax check (app.py, core/, src/, routes/)
    ↓  Gate 2: ruff lint (warn-only — upstream style is their problem)
    ↓  Gate 3: pytest smoke tests (skipped in CI with --skip-tests)
integration  [ff-only merge + LKG-TIMESTAMP tag]
    ↓  (manual merge — done after reviewing what landed)
develop
```

### Running the pipeline manually

```bash
# Must be on integration branch before running
git checkout integration

# Full sync (runs all gates + promotes to integration)
python3 tooling/sync-upstreams/upstream_ingest_pipeline.py

# Dry run — runs gates only against current state, no commits
python3 tooling/sync-upstreams/upstream_ingest_pipeline.py --dry-run

# Skip tests (use in CI or if no venv)
python3 tooling/sync-upstreams/upstream_ingest_pipeline.py --skip-tests

# Push integration and tags to origin after sync
python3 tooling/sync-upstreams/upstream_ingest_pipeline.py --push
```

### CI runs automatically

`.github/workflows/sync-upstream.yml` runs the pipeline daily at 3am UTC with `--skip-tests --push`. Check `origin/integration` after 3am UTC to see if new upstream commits landed.

### Promoting integration to develop

The pipeline lands changes on `integration`. To get them into `develop`:

```bash
git checkout develop
git merge integration
# Resolve any conflicts (rare — protected files are restored by pipeline)
git push origin develop
```

This is a manual step: the pipeline does not auto-merge to `develop`. Review what landed on `integration` before merging.

### What the pipeline protects

The pipeline restores these files to their `integration` state after every upstream merge, preventing upstream from overwriting fork-specific code:

| Protected | Why |
|-----------|-----|
| `tooling/sync-upstreams/upstream_ingest_pipeline.py` | The pipeline itself |
| `.github/workflows/sync-upstream.yml` | Fork-only workflow; does not exist upstream |
| `.env.example` | Fork may add env vars upstream doesn't have |
| `README.md` | Fork uses `assets/` paths; upstream uses `docs/` |

To add a new fork-specific file to protection, add it to `PROTECTED_FILES` in the pipeline source. To protect an entire directory, suffix the path with `/`; the pipeline uses `git checkout ref -- dir/` and also removes any files upstream added that aren't in the integration ref.

**Note on `.github/workflows/`:** The whole directory was previously protected but that froze all upstream workflow improvements. Now only `sync-upstream.yml` is protected. Upstream's other workflow files (ci.yml, issue-description-check.yml, pr-description-check.yml, etc.) flow through normally.

### How the pipeline handles the assets/ move

This fork moved upstream's media files (`docs/*.gif`, `docs/*.webm`, etc.) to `assets/`. Upstream still keeps them in `docs/`. Every time a sync merge runs, upstream may re-add those files to `docs/`; the pipeline removes them automatically.

**Automation**: `_restore_protected_files` in the pipeline iterates `docs/` after every merge and removes any file whose extension is in `_MOVED_TO_ASSETS_EXTS` **and** whose canonical copy already exists in `assets/`. This means:

- The file must exist in `assets/` for the `docs/` copy to be removed. If you add a new media file, add it to `assets/`, not `docs/`.
- Supported extensions: `.gif .webm .jpg .jpeg .png .svg .webp`. If upstream ever adds a new media format, add its extension to `_MOVED_TO_ASSETS_EXTS` in the pipeline source.
- Only the top level of `docs/` is scanned. Subdirectory media (e.g. `docs/images/foo.png`) is not cleaned automatically. Add explicit `PROTECTED_FILES` entries or extend the scan if needed.

This automation is why the `refactor/assets-move` branch (issue #19) is safe to contribute upstream: we can accept the PR merge there while the pipeline keeps our `docs/` clean on every subsequent sync.

### When the pipeline fails

**Gate failure (syntax/tests):** Upstream introduced a regression. Do NOT bypass the gate. Investigate what broke. Options:
1. File an upstream issue; wait for them to fix it
2. Apply a minimal fix on the staging branch, then re-run gates
3. If urgent: run `--dry-run` to understand scope, then decide

**Merge conflict:** The pipeline aborts and prints the conflicting files. Resolve manually:

```bash
# Pipeline left you on integration. Switch to the staging branch it created:
git checkout sync/staging-TIMESTAMP
# Resolve conflicts in the listed files
git add <resolved files>
git commit -m "chore(sync): resolve merge conflict with upstream"
# Re-run the pipeline (it will skip sync since staging already exists... or just promote manually)
git checkout integration
git merge --ff-only sync/staging-TIMESTAMP
git tag -a LKG-MANUAL -m "Last Known Good — manual conflict resolution"
git branch -D sync/staging-TIMESTAMP
```

**Pre-flight failure:** Most common causes:
- Not on `integration` branch -> `git checkout integration`
- Uncommitted changes -> `git stash` or commit them
- Missing `upstream` remote -> `git remote add upstream git@github.com:odysseus-dev/odysseus.git`
- No venv (full run only) -> `python3 -m venv venv && venv/bin/pip install -r requirements.txt`

---

## Upstream Pull Request Procedure

Agents do not file upstream PRs. The human author files them. The agent's job is to ensure the branch is clean and ready.

**Full filing guide:** `docs/dev/filing-guide.md` covers issue templates, PR template fields, the issue-drafts workflow, "How to Test" requirements, screenshot rules, the LLM agent policy, and common mistakes. Read it before filing.

**What "ready to file" means:**
- Branch starts from `upstream-mirror` (verify: `git log --oneline upstream-mirror..fix/branch-name` shows only your commit(s))
- Contains only the files relevant to the specific fix, nothing fork-specific
- Single clean commit with a clear message
- No hardcoded user-specific paths
- Tests pass locally
- For UI changes: screenshots captured (required; PR will be closed without them)
- PR draft in `docs/fork/upstream/pr-drafts/` has a complete "How to Test" section (required; PR will be sent back without it)
- Upstream issue draft exists in `docs/fork/upstream/issue-drafts/` (required for all branches)

**When you are ready to file:**
1. Open the issue draft in `docs/fork/upstream/issue-drafts/<name>.md`
2. File the issue on the upstream repo, pasting the title and body from the draft
3. Fill the assigned issue number into `Fixes #` in the PR draft
4. Open PR: `<your-fork>:<branch>` -> `odysseus-dev/odysseus:dev`
5. Record the upstream issue # and PR # in `docs/fork/upstream/pr-status.md`

All upstream PRs target `upstream:dev`, never `upstream:main`.

---

## Quick Reference: Common Mistakes to Avoid

| Mistake | Why bad | Correct action |
|---------|---------|----------------|
| Classifying work as fork-only without a specific reason | Prevents valid upstream contributions; breaks issue tracking | Default to upstream-candidate; fork-only is only the sync pipeline, fork CI, and fork management docs |
| Branching an upstream-candidate off `develop` | Pollutes branch with 100+ fork commits; PR would be unusable | Branch from `origin/upstream-mirror` |
| Committing to `upstream-mirror` | Commits destroyed on next sync | Use `upstream-mirror` as branch origin only; never commit there |
| Cherry-picking from `upstream/dev` directly to `develop` | Bypasses gates; no syntax/lint/test verification | Run the ingest pipeline |
| Merging an upstream-candidate branch to `develop` | Would import upstream history into develop | Cherry-pick specific commits to develop |
| Filing upstream PR from an agent | Upstream CONTRIBUTING.md prohibits it; the human author must file | Stage the branch; update pr-status.md; the human files |
| Closing an issue before verifying the fix works | Disrupts workflow tracking | Verify first, close after |
| Creating a branch without an issue | Untraceable work | Create issue first, always |
| Editing `develop` directly for upstream-candidate work | Creates untracked work with no branch/issue/PR | Branch from upstream-mirror, commit there, cherry-pick to develop |
| Forgetting to update docs | Future agents and contributors lack context | Update `changes-from-upstream.md` for new/modified files |

---

## Rebasing a Staging Branch

When `upstream-mirror` advances (after an upstream sync), staging branches need rebasing so they apply cleanly on top of current upstream code.

```bash
git log --oneline fix/branch-name..upstream-mirror | wc -l   # if > 0, rebase needed
git checkout fix/branch-name
git rebase upstream-mirror
```

**Conflict resolution:** Read both sides. Keep your fix AND incorporate upstream's changes. Remove all conflict markers. `git add <file> && git rebase --continue`.

**If stuck:** `git rebase --abort` to return to pre-rebase state.

**After rebase:** Develop's cherry-picks may be stale. Verify with `git diff upstream-mirror develop -- <files>`. If develop shows regressions, re-cherry-pick the rebased commit.

## Cherry-Picking to Develop

```bash
git checkout develop
git cherry-pick <commit-hash>
```

**Conflict resolution:** `git checkout --theirs <file>` takes the cherry-picked version (usually what you want). Then `git add <file> && git cherry-pick --continue`.

**Verifying the cherry-pick landed:** `git diff origin/develop -- <file>` should show your expected changes. If the file looks wrong, `git checkout origin/develop -- <file>` to reset, then re-cherry-pick.

## Pre-Flight Checklist (before marking "Ready to File")

- [ ] Branch starts from `upstream-mirror` (not `develop`)
- [ ] Single clean commit (or tightly related commits)
- [ ] Diff contains only intended files, no fork-specific content
- [ ] No hardcoded paths, usernames, or tokens
- [ ] Commit message is clear and written for upstream reviewers
- [ ] `python -m py_compile` passes on changed Python files
- [ ] `node --check` passes on changed JS files
- [ ] Cross-platform considered: no Linux-only assumptions in shared code
- [ ] Documentation updated: `changes-from-upstream.md` for new/modified files
