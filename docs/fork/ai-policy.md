# AI Policy: jdmanring/odysseus Fork

> **Fork operating rules.** These constraints apply only in this workbench fork.
> They are stricter than upstream's `CONTRIBUTING.md` in some areas and add rules
> that upstream has no reason to know about. Upstream AI guidance lives in
> `docs/ai/RULES.md`; this document covers the fork workbench itself.

---

## Purpose of This Fork

This fork is a contribution workbench, not a divergent product. Its purpose is to
develop and stage upstream pull requests to `odysseus-dev/odysseus`. Every
fix, feature, and document defaults to upstream-candidate. Fork-only is the narrow
exception: the sync pipeline (`tooling/sync-upstreams/`), the fork CI workflow
(`sync-upstream.yml`), and the fork management docs (`docs/fork/`). Everything else
(the Qt wrapper, the download stack, the AI documentation, all application code and
docs) belongs upstream. When in doubt, assume upstream-candidate.

---

## Hard Rules

**No sudo.** If an operation requires elevated privileges, write the command for the
user to run; do not execute it yourself.

**Issue before branch.** Create the tracking entry in the **local** tracker
(`docs/fork/issues/`) before creating any branch. No branch exists without one.

The workbench repo (`jdmanring/odysseus-workbench`) has GitHub Issues **disabled by
design**: it exists to stage upstream PRs, not to receive public contributions, and a
GitHub tracker on it only added confusion. `docs/fork/issues/issue-export.json` is the
source of truth (all 168 issues carried over from the retired `jdmanring/odysseus`,
with bodies and comment threads); `INDEX.md` is the committed index; regenerate the
readable view with `python3 tooling/issues_to_markdown.py`.

**Branch when work begins, not when the issue is filed.** Do not pre-stage a
branch at issue-filing time. A branch created "for later" sits empty, and an
empty branch is indistinguishable-at-a-glance from one whose work was lost:
a month later it reads as a robbery and costs an investigation to disprove
(this happened: `perf/cdp-listener-audit`, created within a minute of issue #76
in June 2026, pushed empty, and flagged as suspected lost work in July). The
issue alone is the parking spot for planned work; create the branch in the same
session the first commit lands.

**Search upstream prior art before staging.** Before opening the issue for any
upstream-candidate work, search the upstream repo for the same problem area:
issues, PRs, discussions, and `ROADMAP.md`.
`gh issue list --repo odysseus-dev/odysseus --search "<terms>" --state all`
(and `gh pr list ...`). Record the result in the fork issue and the PR draft: link
related items, and state plainly whether the work **duplicates**, **complements**, or
**conflicts** with an in-flight PR (a conflict, e.g. two competing approaches to the
same problem, needs maintainer coordination, not a parallel PR). Upstream's PR template
requires "I searched open issues and open PRs"; the staged draft must honestly reflect
that search, not just tick the box. Skipping this is how a contribution gets closed as a
duplicate or lands next to a better existing proposal.

**Never push to the `upstream` remote.** The `upstream` remote is
`odysseus-dev/odysseus`, which is read-only. Never push there under any circumstances.

**Never file issues or PRs on upstream without explicit per-action authorization.**
Agents stage work on clean branches; the human author files. Upstream's CONTRIBUTING.md
prohibits agent-filed PRs.

**Never commit to `upstream-mirror`.** This branch is reset-only. Any commits are
destroyed on the next sync.

**Never cherry-pick upstream -> `develop` directly.** Use the ingest pipeline:
`tooling/sync-upstreams/upstream_ingest_pipeline.py` -> promotes to `integration` ->
merge to `develop`. This preserves gate verification and a clean merge history.

**Branch origin matters.** Upstream-candidate branches must start from `upstream-mirror`,
not `develop`. Fork-only branches start from `develop`. Getting this wrong contaminates
upstream PRs with fork history. Full rules: `docs/dev/git-branch-workflow.md`.

**Never close issues without verification.** An issue is closed only when the fix is
confirmed working, not when you believe you have applied a fix. What "confirmed working"
means depends on issue type:

- **Fork-only issues**: close when the fix is verified on `develop`.
- **Upstream-candidate issues**: stay open until the upstream PR is filed. The filed PR
  is what closes the loop; until then the issue is the only active tracker for that work.

**Never classify work as fork-only without a specific reason it cannot go upstream.**
"It touches new files" or "it's a big feature" are not reasons. The Qt wrapper, the
aria2c download stack, and the AI documentation are all upstream-candidate despite
being new or fork-originated.

**Never modify `CONTRIBUTING.md`.** It is upstream's document. Fork-specific contributor
guidelines belong here and in `CLAUDE.md`, not in `CONTRIBUTING.md`.

---

## Definition of Done: Tracking Step

After implementation and verification (see `docs/ai/RULES.md`), sync all fork tracking:

- Update the corresponding PR draft in `docs/fork/upstream/pr-drafts/`.
- Update `docs/fork/active-work.md` (status, branch name).
- Update `docs/fork/upstream/pr-status.md`.
- Update `docs/fork/changes-from-upstream.md` for any new or modified files.

Do not mark a branch "Ready to File" until all four are current.

---

## Fork Operations: Step-by-Step Procedures

These are the exact procedures for maintaining the fork pipeline. Follow them in order.
Do not improvise.

### 0. Always Start Here and Read the State

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
- Gate 2 is warn-only; upstream style is not our problem.

**If the pipeline reports a merge conflict:**
```bash
# Pipeline leaves you on the sync/staging-TIMESTAMP branch
git checkout sync/staging-TIMESTAMP   # (it prints the exact name)
# Open the conflicting files, resolve them, then:
git add <resolved files>
git commit -m "chore(sync): resolve merge conflict with upstream"
git checkout integration
git merge --ff-only sync/staging-TIMESTAMP
git tag -a LKG-MANUAL -m "Last Known Good: manual conflict resolution"
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
Protected files (pipeline script, fork CI, README, .env.example) should be
auto-restored by the pipeline. Any remaining conflict is in application code. Resolve
by keeping develop's version of fork-specific code and accepting upstream's changes to
everything else. Never discard upstream fixes to make a conflict disappear.

```bash
git add <resolved files>
git commit   # merge commit message is fine
```

---

### 3. Rebasing a Staging Branch

Staging branches (`fix/*`, `feat/*`, `refactor/*`) were created from `upstream-mirror`
at some point in the past. When upstream-mirror advances, the staging branch needs
to be rebased so commits apply cleanly on top of current upstream code.

**When to rebase:**
- Before filing a PR upstream (required: PR must apply to current upstream:dev)
- When the branch base is behind the current upstream-mirror tip

**Check if rebase is needed:**
```bash
git log --oneline fix/branch-name..upstream-mirror | wc -l
# If > 0, the staging branch is behind upstream-mirror and needs rebasing
```

**Rebase procedure:**
```bash
git checkout fix/branch-name
git rebase upstream-mirror
```

**If the rebase completes with no conflicts:** Verify it looks right:
```bash
git log --oneline upstream-mirror..fix/branch-name   # ONLY our commit(s)
git diff upstream-mirror fix/branch-name             # ONLY our intended changes
```

**If conflicts occur during rebase:**

Git will pause and show the conflicting files. For each conflict:

1. Open the conflicting file. Conflict markers:
   ```
   <<<<<<< HEAD          ← current upstream-mirror content
   (upstream code)
   =======
   (our code)
   >>>>>>> <commit>      ← our commit being replayed
   ```

2. **Keep our fix AND keep upstream's other changes.** Do not just accept one side.
   Read both sides. Merge them: incorporate our change into the upstream version.

3. Remove all conflict markers. The file must be valid code.

4. ```bash
   git add <resolved file>
   git rebase --continue
   ```

5. Repeat for each commit being replayed.

**If stuck:** `git rebase --abort` to return to pre-rebase state. Ask before retrying.

**After rebase, verify develop:**
```bash
git diff upstream-mirror develop -- <files changed by this staging branch>
```
- Diff shows only our expected fix -> develop is correct, no action needed.
- Diff shows unexpected regressions -> develop needs updating. See step 4.

---

### 4. Fixing Develop After a Rebase

**Only do this if step 3's verification showed develop has unexpected regressions.**

```bash
git checkout develop

NEW_HASH=$(git log --format="%H" upstream-mirror..fix/branch-name | tail -1)

git checkout upstream-mirror -- <file1> <file2>
git cherry-pick $NEW_HASH
```

**For staging branches with multiple commits, cherry-pick oldest first:**
```bash
git log --reverse --format="%H" upstream-mirror..fix/branch-name
git cherry-pick <hash1>
git cherry-pick <hash2>
```

---

### 5. Creating a New Staging Branch

**First: create the tracking entry** in the local tracker. Append an object to
`docs/fork/issues/issue-export.json` (take the next free number; the highest so far is
recorded at the top of `INDEX.md`), then regenerate:
```bash
python3 tooling/issues_to_markdown.py   # rewrites INDEX.md (committed) + README.md (ignored)
```
The branch must not exist until the entry does. GitHub Issues are disabled on the
workbench by design; do not try `gh issue create` against it.

**Then: create the branch from upstream-mirror (NOT from develop).**
```bash
git fetch origin upstream-mirror
git checkout -b fix/short-description upstream-mirror
# Do the work: only files relevant to this fix
git add <specific files only>
git commit -m "fix: description. Fixes #<issue-number>"

# Cherry-pick to develop so the fix is live in the working branch
git checkout develop
git cherry-pick <commit-hash>
git checkout fix/short-description   # keep staging branch: it is the PR candidate
```

**Verify origin is correct before anything else:**
```bash
git log --oneline | tail -5   # should show upstream commits, not develop's fork history
```
If you see fork-specific commits (docs/fork/, CLAUDE.md, etc.) in the tail, the branch
was created from the wrong base. Delete it and start over from `upstream-mirror`.

---

### 6. Squashing a Staging Branch to One Clean Commit

Before filing a PR upstream, a staging branch should have a single clean commit.

```bash
git checkout fix/branch-name
git rebase -i upstream-mirror
# In the editor: keep first commit as 'pick', change the rest to 'squash' or 'fixup'
```

After squashing, develop's cherry-picks are stale. Run step 4 to bring develop current.

---

### 7. Cherry-Picking to Develop

```bash
git checkout develop
git cherry-pick <commit-hash>
```

**Conflict resolution:** `git checkout --theirs <file>` takes the cherry-picked version
(usually what you want). Then `git add <file> && git cherry-pick --continue`.

**Verifying the cherry-pick landed:** `git diff origin/develop -- <file>` should show
your expected changes. If the file looks wrong, `git checkout origin/develop -- <file>`
to reset, then re-cherry-pick.

---

## Hard Stops (Never Do These)

| Never | Because |
|-------|---------|
| `git push upstream ...` | Pushes to odysseus-dev/odysseus, which is strictly read-only |
| `git push --force origin develop` | Destroys history; develop is the primary working branch |
| `git push --force origin fix/*` after a PR is filed | Breaks the PR; upstream reviewers lose context |
| `git rebase develop` on a staging branch | Contaminates it with fork history; unusable as a PR |
| `git merge develop` on a staging branch | Same problem |
| Cherry-pick from `upstream/dev` to `develop` directly | Bypasses all pipeline gates |
| Close an upstream-candidate issue before filing the upstream PR | Issue is the only active tracker until the PR exists |
| Creating a branch without an issue | Untraceable work |
| Editing `develop` directly for upstream-candidate work | Creates untracked work with no branch/issue/PR |
| Forgetting to update fork tracking docs | Future contributors lack context |
| Modifying `CONTRIBUTING.md` | It is upstream's document |

---

## Pre-Flight Checklist (before marking "Ready to File")

- [ ] Branch starts from `upstream-mirror` (not `develop`)
- [ ] Single clean commit (or tightly related commits)
- [ ] Diff contains only intended files, no fork-specific content (CLAUDE.md, docs/fork/)
- [ ] No hardcoded paths, usernames, or tokens
- [ ] Commit message is clear and written for upstream reviewers
- [ ] `python -m py_compile` passes on changed Python files
- [ ] `node --check` passes on changed JS files
- [ ] Cross-platform considered: no Linux-only assumptions in shared code
- [ ] All fork tracking updated: PR draft, active-work.md, pr-status.md, changes-from-upstream.md
