# AI Rules — Odysseus

> **The Law.** This document contains hard constraints, the Git pipeline, and non-negotiable policies.

---

## Core Mandates

**Read the source before writing code.** Find the relevant file, read it, report what
you find. Do not generate code against an assumption about what the code looks like.

**No sudo.** If an operation requires elevated privileges, write the command for
the user to run — do not execute it yourself.

**Issue before PR.** Upstream explicitly requires an issue to exist before any PR
is filed. This applies to agent-generated work as well — see `CONTRIBUTING.md` for
the full policy on agent PRs.

**One thing per PR.** No mixing unrelated fixes, formatting changes, or refactors into
a single PR. Each PR must be reviewable in isolation.

**Verify the fix in the running app.** Tests are not sufficient. Before any PR is
considered ready, the fix must be confirmed end-to-end in the actual application.

**Verification Protocol:**
1. **Logs:** Tail the terminal running `app.py` or check the `logs/` directory for tracebacks.
2. **Tests:** Run `pytest tests/[feature_name]` to ensure no regressions.
3. **UI:** Perform the specific user action in the browser that triggered the bug.

**Lifecycle Ownership & Definition of Done**
You are an engineer, not a script. A task is not "done" when the code is written; it is done when the entire delivery chain is complete. Do not wait to be prodded to perform trailing tracking tasks.

**The Definition of Done:**
1. **Implementation**: Code is written, linted, and committed to the correct branch.
2. **Verification**: The fix is verified via the Verification Protocol above.
3. **Tracking**: All project tracking is synced:
   - Update `docs/fork/issue-tracker.md` (e.g., mark as "Ready to File").
   - Update the corresponding PR draft in `docs/fork/upstream/pr-drafts/`.
   - Update `docs/fork/upstream/pr-status.md`.
4. **Reporting**: Report the final state and explicitly confirm that all tracking is updated.

**Visual changes require screenshots.** Any PR touching `static/js/`, HTML, or CSS
must include a screenshot or clip. See `CONTRIBUTING.md` for details.

**Use existing constants and helpers.** Never hardcode paths, ports, or URLs that
the project already exposes. See `CONTRIBUTING.md` — Code conventions.

---

## Fork-Specific Rules (jdmanring/odysseus only)

These rules apply only when working in this fork. They have no meaning in the
upstream source project.

**This fork is a contribution workbench.** Its purpose is to develop and stage upstream
pull requests to `pewdiepie-archdaemon/odysseus`. Every fix, feature, and document
defaults to upstream-candidate. Fork-only is the narrow exception: the sync pipeline
(`tooling/sync-upstreams/`), the fork CI workflow (`sync-upstream.yml`), and the fork
management docs (`docs/fork/`, `docs/dev/git-branch-workflow.md`). Everything else —
including `docs/ai/CONTEXT.md`, `docs/ai/RULES.md`, the Qt wrapper, the download stack, all
application documentation — belongs upstream. When in doubt, assume upstream-candidate.

- **Never push to the `upstream` remote** or file issues/PRs there without James's
  explicit per-action authorization. Agents stage work on clean branches; James files the PRs.
- **Never commit to `upstream-mirror`.** This branch is reset-only; any commits are lost on next sync.
- **Never cherry-pick upstream → `develop` directly.** Use the sync pipeline:
  `tooling/sync-upstreams/upstream_ingest_pipeline.py` → promotes to `integration` → merge to `develop`.
- **Branch origin matters.** Upstream-candidate branches must start from `upstream-mirror`, not `develop`.
  Fork-only branches start from `develop`. Getting this wrong contaminates upstream PRs with fork history.
  Full rules: `docs/dev/git-branch-workflow.md`.
- **Never close issues without verification.** An issue is closed only when the fix is confirmed working.
- **Never classify work as fork-only without a specific reason it cannot go upstream.**
  "It touches new files" or "it's a big feature" are not reasons. The Qt wrapper, the aria2c
  download stack, and the AI documentation are all upstream-candidate despite being new.

---

## Fork Operations — Step-by-Step Procedures

These are the exact procedures for maintaining the fork pipeline. Follow them in order.
Do not improvise. When in doubt, stop and ask James.

### 0. Always Start Here — Read the State

Before any operation, check where things stand:

```bash
# New upstream commits not yet in upstream-mirror?
git fetch upstream
git log --oneline upstream/dev ^upstream-mirror

# Is develop behind integration?
git log --oneline integration ^develop

# Which staging branches exist and how many commits do they have?
git log --oneline upstream-mirror..fix/branch-name   # repeat per branch
```

Active branches and their status are tracked in `docs/fork/active-work.md` and
`docs/fork/upstream/pr-status.md`. Read those before touching any branch.

---

### 1. Running the Ingest Pipeline

Use this when `git log upstream/dev ^upstream-mirror` shows new commits.

**Prerequisite:** Must be on the `integration` branch. Must have no uncommitted changes.

```bash
git checkout integration
python3 tooling/sync-upstreams/upstream_ingest_pipeline.py --skip-tests
```

Expected output ends with: `[OK] Pipeline complete. LKG tag: LKG-YYYYMMDD-HHMM`

**If a gate fails (Gate 1 = syntax, Gate 2 = lint, Gate 3 = tests):**
- Do NOT pass `--skip-tests` to bypass Gate 3 unless you already were.
- Do NOT add `# noqa` or ignore the failure.
- Gate 1/3 failure means upstream introduced a regression. File an upstream issue; wait for a fix.
- Gate 2 is warn-only — upstream style is not our problem.

**If the pipeline reports a merge conflict:**
```bash
# Pipeline leaves you on the sync/staging-TIMESTAMP branch
git checkout sync/staging-TIMESTAMP   # (it prints the exact name)
# Open the conflicting files, resolve them, then:
git add <resolved files>
git commit -m "chore(sync): resolve merge conflict with upstream"
git checkout integration
git merge --ff-only sync/staging-TIMESTAMP
git tag -a LKG-MANUAL -m "Last Known Good — manual conflict resolution"
git branch -D sync/staging-TIMESTAMP
```

---

### 2. Promoting Integration to Develop

After the pipeline completes, integration has new upstream commits. Promote them:

```bash
git checkout develop
git merge integration
```

**If conflicts occur here:**
Protected files (pipeline script, fork CI, README, .env.example) should be auto-
restored by the pipeline. Any remaining conflict is in application code. Resolve by
keeping develop's version of our fork-specific code and accepting upstream's changes
to everything else. Never discard upstream fixes to make a conflict disappear.

```bash
git add <resolved files>
git commit   # merge commit message is fine
```

---

### 3. Rebasing a Staging Branch

Staging branches (`fix/*`, `feat/*`, `refactor/*`) were created from `upstream-mirror`
at some point in the past. When upstream-mirror advances, the staging branch needs
to be rebased so our commit(s) apply cleanly on top of the current upstream code.

**When to rebase:**
- Before filing a PR upstream (required — PR must apply to current upstream:dev)
- When James asks for it
- When `git log upstream-mirror..fix/branch-name` shows commits that include upstream
commits (i.e., the branch base is behind the current upstream-mirror tip)

**Check if rebase is needed:**
```bash
# Count how many commits upstream-mirror has that are NOT in the staging branch
git log --oneline fix/branch-name..upstream-mirror | wc -l
# If > 0, the staging branch is behind upstream-mirror and needs rebasing
```

**Rebase procedure (one staging branch at a time):**

```bash
git checkout fix/branch-name
git rebase upstream-mirror
```

**If the rebase completes with no conflicts:** Verify it looks right:
```bash
# Should show ONLY our commit(s) — nothing else
git log --oneline upstream-mirror..fix/branch-name

# Should show ONLY our intended changes — no upstream regressions, no extra files
git diff upstream-mirror fix/branch-name
```

**If conflicts occur during rebase:**

Git will pause and show the conflicting files. For EACH conflict:

1. Open the conflicting file. You will see conflict markers:
   ```
   <<<<<<< HEAD          ← this is the current upstream-mirror content
   (upstream code)
   =======
   (our code)
   >>>>>>> <commit>      ← this is our commit being replayed
   ```

2. **The goal: keep our fix AND keep upstream's other changes.**
   - DO NOT just accept `<<<<<<< HEAD` (theirs) — that discards our fix.
   - DO NOT just accept `>>>>>>> commit` (ours) — that may discard upstream fixes.
   - Read both sides. Merge them: incorporate our change into the upstream version.

3. Remove all conflict markers. The file must be valid code when done.

4. ```bash
   git add <resolved file>
   git rebase --continue
   ```

5. Repeat for each commit being replayed. If the same file conflicts on multiple
commits, you may need to resolve it more than once.

**If you are stuck on a conflict and cannot safely merge both sides:**
```bash
git rebase --abort   # puts branch back to pre-rebase state, nothing lost
```
Then stop and ask James before retrying.

**After rebase, check develop:**

The staging branch was previously cherry-picked to `develop`. After rebasing, the
cherry-pick on develop may reference an outdated commit hash — but the NET RESULT
on develop is often still correct (develop has both upstream changes AND our fix).

Always verify:
```bash
# Do develop's changed files show only our expected changes on top of upstream?
git diff upstream-mirror develop -- <files changed by this staging branch>
```

- If the diff shows only our expected fix — develop is correct. No action needed.
- If the diff shows unexpected regressions (upstream code got overwritten) — develop
  needs updating. See "Fixing Develop After a Rebase" below.

---

### 4. Fixing Develop After a Rebase (only if verification shows a problem)

**Only do this if step 3's verification showed develop has unexpected regressions.**

```bash
git checkout develop

# Get the new commit hash from the rebased staging branch
NEW_HASH=$(git log --format="%H" upstream-mirror..fix/branch-name | tail -1)
# (use tail -1 for the oldest commit if there are multiple; cherry-pick in order)

# Restore the affected file(s) to their upstream-mirror state, then re-apply
git checkout upstream-mirror -- <file1> <file2>
git cherry-pick $NEW_HASH
```

**If the staging branch has multiple commits, cherry-pick them in order (oldest first):**
```bash
# List commits oldest-first
git log --reverse --format="%H" upstream-mirror..fix/branch-name

# Cherry-pick each one
git cherry-pick <hash1>
git cherry-pick <hash2>
...
```

---

### 5. Creating a New Staging Branch

This is how all new upstream-candidate work starts.

**First: create the issue.**
```bash
gh issue create --repo jdmanring/odysseus --title "..." --body "..."
# Note the issue number — the branch must not exist until the issue does
```

**Then: create the branch from upstream-mirror (NOT from develop).**
```bash
# Always fetch first so upstream-mirror is current
git fetch origin upstream-mirror

git checkout -b fix/short-description upstream-mirror
# Do the work — only files relevant to this fix
git add <specific files only>
git commit -m "fix: description — Fixes #<issue-number>"

# Cherry-pick to develop so the fix is live in our working branch
git checkout develop
git cherry-pick <commit-hash>
git checkout fix/short-description   # keep staging branch — it's the PR candidate
```

**Verify origin is correct before anything else:**
```bash
git log --oneline | tail -5   # should show upstream commits, not develop's fork history
```
If you see fork-specific commits (docs/fork/, CLAUDE.md, linux_wrapper.py, etc.)
in the tail of the log, the branch was created from the wrong base. Delete it and
start over from `upstream-mirror`.

---

### 6. Squashing a Staging Branch to One Clean Commit

Before filing a PR upstream, a staging branch should have a single clean commit
(or a small number of tightly related commits). Multi-commit branches need squashing.

```bash
git checkout fix/branch-name

# Count how many commits are ours
OURS=$(git log --oneline upstream-mirror..fix/branch-name | wc -l)

# Interactive rebase to squash
git rebase -i upstream-mirror
# In the editor: keep first commit as 'pick', change the rest to 'squash' or 'fixup'
# Write a clean commit message that explains the complete fix
```

After squashing, develop's cherry-picks are stale (they referenced individual commits).
Run the "Fixing Develop After a Rebase" procedure to bring develop current.

---

### 7. Verification Checklist Before Marking a Branch "Ready to File"

Run this for every staging branch before updating its status in pr-status.md:

```bash
# 1. Branch starts from current upstream-mirror (zero commits from upstream-mirror in our range)
git log --oneline upstream-mirror..fix/branch-name   # should show ONLY our commit(s)

# 2. Diff is exactly the intended fix — no extra files, no debug code, no fork-specific paths
git diff upstream-mirror fix/branch-name

# 3. No fork-specific content in the diff (CLAUDE.md, docs/fork/, linux_wrapper.py, etc.)
git diff upstream-mirror fix/branch-name --name-only

# 4. Single clean commit (for most fixes)
git log --oneline upstream-mirror..fix/branch-name | wc -l   # ideally 1

# 5. Commit message is clear and written for upstream reviewers (not for this fork)
git log -1 --format="%s%n%b" fix/branch-name
```

---

### Hard Stops — Never Do These

| Never | Because |
|-------|---------|
| `git push upstream ...` | Pushes to pewdiepie-archdaemon/odysseus — strictly read-only |
| `git push --force origin develop` | Destroys history; develop is the primary working branch |
| `git push --force origin fix/*` AFTER a PR is filed | Breaks the PR; upstream reviewers lose context |
| `git rebase develop` on a staging branch | Contaminates it with fork history — branch is now unusable as a PR |
| `git merge develop` on a staging branch | Same problem as above |
| Cherry-pick from `upstream/dev` to `develop` directly | Bypasses all pipeline gates |
| Close an issue before the fix is confirmed working | Disrupts workflow tracking |
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

**If stuck:** `git rebase --abort` to return to pre-rebase state. Ask James before retrying.

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
- [ ] Diff contains only intended files — no fork-specific content
- [ ] No hardcoded paths, usernames, or tokens
- [ ] Commit message is clear and written for upstream reviewers
- [ ] `python -m py_compile` passes on changed Python files
- [ ] `node --check` passes on changed JS files
- [ ] Cross-platform considered: no Linux-only assumptions in shared code
- [ ] Documentation updated: `changes-from-upstream.md` for new/modified files
