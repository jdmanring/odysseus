# Post-Ingest Checklist

Run this after an upstream ingest merge lands on `develop`. Fork-only.

> **Before anything: `git fetch origin && git checkout integration && git reset
> --hard origin/integration`.** A local `integration` that has drifted from origin
> will let the pipeline promote onto the wrong base, and the result looks
> successful. See #180, where exactly that happened and only a rejected push
> prevented it from overwriting the real branch.
>
> **Running the pipeline itself:** follow `docs/dev/git-branch-workflow.md` as
> written. The workaround that used to live here is obsolete as of the 2026-08-03
> re-baseline (`104118b6`): `integration` now carries
> `tooling/sync-upstreams/upstream_ingest_pipeline.py` byte-identical to
> `develop`'s, plus all four `PROTECTED_FILES`, so `_restore_protected_files` is
> live again rather than checking out from a ref that lacks them and being
> swallowed by `check=False`. Confirm before trusting it, since it is a property
> of a branch and not of this file:
>
> ```bash
> git cat-file -e integration:tooling/sync-upstreams/upstream_ingest_pipeline.py
> ```

The pipeline itself (`docs/dev/git-branch-workflow.md`) covers getting upstream's
commits onto `integration` and then `develop`. This covers what has to happen
*after* that, to the ~100 staged contribution branches and the records that
describe them.

Every step has a measured failure behind it. The cost of skipping one is in the
right-hand column, not hypothetical.

| # | Step | What it caught, measured |
|---|------|--------------------------|
| 1 | Rebase staged branches onto the new mirror | 81 branches. Using `merge-base` instead of the old mirror tag makes a 2-commit branch try to replay ~1,900 commits |
| 2 | Verify no work was lost | Line-set diffing reported ~3,100 false losses on 3 branches, identical content each time: a base mismatch, not loss. `git range-diff` is the instrument |
| 3 | Unstaged-work audit | Found a fix sitting on `develop`, unstaged, for 12 days (#175) |
| 4 | Draft file-claims | 5 PR drafts naming files their branch does not contain (#178) |
| 5 | Staged-branch convergence guard | 2 staged files silently lagging `develop` (#131) |
| 6 | Code-graph re-rank | A large merge changes what is central; nothing else reports that |
| 7 | Full suite + leak check | 10 Playwright failures that looked like regressions were `/tmp` exhaustion (#174) |

---

## 1. Rebase the staged branches

```bash
# Tag the mirror BEFORE the pipeline resets it -- there is no way to recover it after.
git tag preingest-$(date +%Y%m%d-%H%M)/upstream-mirror upstream-mirror

python3 tooling/merge/branch_survey.py                      # what already landed, by patch-id
python3 tooling/merge/rebase_staged.py --old-mirror <tag>   # DRY RUN by default
python3 tooling/merge/rebase_staged.py --old-mirror <tag> --apply
```

`--old-mirror` is mandatory and there is no `--dry-run`: omitting `--apply` *is*
the dry run. The tool refuses to infer the old mirror, deliberately.

**Rebase onto the OLD mirror tag, never `merge-base`.** `upstream-mirror` is
RESET by the pipeline, not fast-forwarded, so `merge-base <branch> upstream-mirror`
returns an ancient ancestor:

```bash
git rebase --onto upstream-mirror <old-mirror-tag> <branch>
```

Rollbacks land at `refs/prerebase/<branch>`. **Push them** -- a rollback that only
exists locally is not a rollback.

## 2. Verify no work was lost

```bash
git range-diff <old-base>..origin/<branch> upstream-mirror..<branch>
```

Read the branch's OWN commits: `=` unchanged, `!` changed by conflict
resolution, `<` only in the old series. On a stale branch the `<` list is mostly
inherited upstream commits, not losses.

Do **not** diff added-line sets against the current mirror. A pre-rebase branch
was built on the old mirror, so every upstream commit since reads as a "loss" --
this produced ~3,100 identical false hits across three branches, and the
identicalness is the tell.

## 3. Unstaged-work audit

Which fork commits on `develop` are on no staged branch?

```bash
git log --no-merges -p --format="commit %H" upstream-mirror..develop | git patch-id --stable
git log --no-merges -p --format="commit %H" <all-branches> ^upstream-mirror | git patch-id --stable
```

Two processes. The naive per-commit form is ~95,000 subprocesses on this repo.
Subtract, drop anything touching only `docs/fork/` or `tooling/sync-upstreams/`,
and read what remains: most will be merge repairs restoring upstream's own code,
with nothing to send back.

## 4. Draft file-claims

```bash
python3 tooling/draft_file_claims.py .
```

Fails when a PR draft names a source file its branch does not contain. Treat hits
as leads: a cross-repo citation and a future-tense proposal both read as claims
to a text matcher.

**Read the coverage line, not just the problem count.** It reports `checked N of
M` and lists every draft it skipped and why. That exists because the count used
to be bare: "83 drafts, 0 problems" read as full coverage while 16 of 99 were
never examined, and widening the header match to the spellings actually in use
(`**Branch**:`, `Branch:`) took it to 94 and immediately surfaced four hits that
the silence had been hiding. A skip is fine; an invisible skip is not.

## 5. Convergence guard

```bash
DATABASE_URL=sqlite:///:memory: venv/bin/python -m pytest tests/test_staged_branch_convergence.py -q
```

## 6. Code-graph re-rank

```bash
graphify update . --no-cluster --force && graphify god-nodes
```

**Why here:** a large external merge changes which symbols the codebase leans on,
and no point query reports that. Measured after the 1,957-commit ingest: 21,148
nodes, 49,727 edges, 15 s. The top hub was `parse_tool_blocks()` at **135 edges**
-- the same function hardened against ReDoS that week. That is a risk ranking for
what to test hardest next, and it cost 15 seconds.

Three things that make the difference between a finding and a false finding:

- **`.graphifyignore` must exist before the build.** It is committed, so a fresh
  clone is fine. `venv/` alone was 29,830 of this repo's 31,594 py/js files (94%)
  -- unfiltered, the ranking is dependency internals. Editing it requires deleting
  `graphify-out/`, not just `update`: exclusions apply on a fresh build only.
- **Verify by node count, not exit status.** `update` silently refuses a rebuild
  yielding fewer nodes than the last one, so an ignore-file edit can look applied
  while you query the old graph.
- **Get the caller count before calling a zero a coverage inversion.** Degree is
  undirected, so it conflates fan-in with fan-out and only fan-in makes a test
  worth writing. `_buildEditor()` scored 82 edges with zero test files, which
  reads as a gap; it is a 659-line DOM constructor with **one** caller
  (`openEditor`, already wrapped in `try/catch` with a user-visible error), so
  its edges are the widgets it builds. Contrast `llm_call_async()` -- 12 lines,
  97 edges, ~40 callers across 27 files. Pre-filter on edges over function
  length: high degree on a short function is fan-in by construction.
- **A zero may also mean the test convention differs.** The frontend is covered
  by source-assertion `*_js.py` tests that assert file text rather than naming
  the symbol, so a name-count zero is not evidence of absence. Two test files
  assert `galleryEditor.js` (six have `editor` in the filename, but four cover
  other editors). Read the tests before reporting a zero.

Then hand each hub you care about to the semantic index
(`mcp__serena__find_referencing_symbols`) for its **caller set**. The graph ranks
and cannot say who calls what; the index returns callers and cannot rank. Act on
the caller set, never on the degree count -- a high degree says a symbol matters,
not what it does.

## 7. Full suite, and check what it leaked

```bash
before=$(ls -1U /tmp | grep -c '^tmp.*\.db$')
DATABASE_URL=sqlite:///:memory: venv/bin/python -m pytest tests/ -q --ignore=tests/bench
after=$(ls -1U /tmp | grep -c '^tmp.*\.db$')
echo "leaked: $((after-before))"
```

`/tmp` is a RAM-backed tmpfs on this machine. When it filled, 10 Playwright tests
failed with `Page.goto: Page crashed` and `ERROR at setup` -- indistinguishable
from a code regression, and two of them were the tests whose job is catching a bad
merge resolution. Before blaming a Playwright failure on the diff, run
`df -h /tmp` and check for orphaned `/tmp/.org.chromium.Chromium.*` files from
crashed browsers.

---

## 8. Attack every guard you wrote. Do not re-read it.

Added 2026-08-04, after a guard that was itself written to replace a decorative
guard turned out to be decorative in a different way, and was caught only because
an independent reviewer attacked it instead of reading it.

A test counts as a guard only once you have built the defect it claims to catch and
watched it fail. Three attacks that have each landed here, none of which re-reading
would have surfaced:

- **Re-introduce the original defect verbatim, in a form the guard did not
  anticipate.** `${m['category']}` defeated a scanner whose "no property read"
  alternative was `[^.]*`: bracket notation has no dot, so a raw read parsed as a
  literal. If the guard cannot catch the exact bug it was written for, it catches
  nothing.
- **Satisfy the assertion with a comment.** Any test asserting a literal is present
  in source passes when that literal survives in a comment, or inside a function
  nothing calls. Mutate to a comment, not to a deletion; deletion is the one
  mutation these always catch.
- **Invert the guard rather than removing it.** `if x in ALLOWED` instead of
  `if x not in ALLOWED` keeps every token a source scan looks for while reversing
  the behaviour.

Then check the other direction: a harmless refactor -- destructuring, renaming,
extracting a helper -- must not fail the suite. A guard that fires on formatting is
testing the formatter.

**Prefer executing to scanning.** Where the target is reachable, call it with a
hostile input. 39 of this repo's 49 `*_js.py` tests already run under node; a source
scanner is a fallback for what genuinely cannot be executed, not a default.

---

## 9. Use lenses that do not share your premises

The steps above are things you run. This one is a thing you cannot run on yourself.

A single reviewer converging proves one lens is exhausted, not that the work is
clean -- and rounds that start returning findings about your own audit prose rather
than the artifact are the signal that you have hit that ceiling, not that you have
passed. Every load-bearing false claim in the 2026-08 staging round was found by a
reviewer who did not inherit the author's premises, and none by re-reading.

Run reviewers in parallel with distinct mandates, blind to each other: hostile
appsec, adversarial test engineer, upstream maintainer under time pressure, records
auditor. Two lenses landing on the same finding independently is what makes it
trustworthy; one lens landing on it repeatedly is not.

The cheapest version of this rule: **before filing anything, ask which claim in it
would be most embarrassing if a stranger checked it, and check that one.**

---

## Record the result

Update `docs/fork/upstream/pr-status.md` with the rebase state, any supersessions
found, and the branches whose status changed. That document is what PRs are filed
from; an ingest that does not update it leaves the next filing pass working from
a stale map.

**When you correct an artifact, correct the rows that DESCRIBE it.** The sweep
above hunts pending/not-yet phrasing and structurally cannot catch this: a
`pr-status.md` row is grammatically fine while describing a claim that has since
been retracted. Measured three times, most recently 2026-08-04, when the #182
drafts were rewritten after a review falsified their central claim and both
state-doc rows still repeated it verbatim -- along with the tracker entry those
rows are generated from, which is the source of truth. Same pass, a branch that
was staged, pushed and drafted (#184) appeared in neither state doc at all.

After any correction or new branch:

```bash
grep -rn "<branch-name>\|#<issue>" docs/fork/ --include="*.md" | grep -v issues/README
```

Every hit is a description that may now be stale, and the tracker JSON is one of
them. Retract in place with a dated banner rather than editing the original text
away -- a record that erases its own mistakes is not a record.

**Check cited commits for REACHABILITY, not existence.** `git cat-file -e <sha>`
answers "does this object exist", which is not the property a doc claim needs. A
rebase leaves the old commit as a loose object, so a citation like "branch X
gained `abc1234`" passes an existence check while the SHA is on no branch at all.
Ask the right question:

```bash
git merge-base --is-ancestor <sha> <branch>          # is it actually on that branch
git for-each-ref --contains <sha> --format='%(refname)'   # what reaches it at all
```

Measured 2026-08-04 across 318 distinct SHAs cited in `docs/fork/`: 173 on a
branch, 37 held only by `refs/prerebase`/`refs/salvage`, and **104 reachable
from no ref whatsoever** -- loose objects that `git gc` prunes once they pass
`gc.pruneExpire` (two weeks; most dated from June). Those citations were weeks
from becoming unresolvable.

They are now pinned at `refs/docsha/<short-sha>` and pushed. That is the cheap
fix: the record stays resolvable without rewriting 104 citations, and the
rewrite would have been churn since the work itself is present under post-rebase
SHAs. **Re-run the scan after any rebase sweep** -- a sweep rewrites every branch
it touches and orphans every SHA the docs cited for them, all at once. Do not
delete `refs/docsha/*`; it is load-bearing for the provenance record.

**Then sweep for the claims the promotion just falsified.** Adding new text is the
easy half; the failure mode is the sentence that was true when written and was
never revisited. Six of them were found this way on 2026-08-03, including two
saying the day's ingest was "not yet promoted to `develop`" hours after it was:

```bash
grep -rn "not yet\|NOT yet\|still pending\|nothing pushed\|is currently\|pending ingest" \
  docs/fork/ --include="*.md" | grep -v "docs/fork/issues/README.md"
```

Pass the **directory**, not `docs/fork/*.md`. The glob expands to files, which
makes `-r` inert and silently limits the sweep to 32 of 225 fork docs -- every
PR draft, issue draft and runbook is in a subdirectory. That mistake shipped in
the first version of this step and is exactly the kind of thing it exists to
catch. `issues/README.md` is generated from `issue-export.json`; edit the JSON
and regenerate rather than acting on a hit there.

Every hit is a claim with a date attached. Check it against git rather than
against memory -- `git merge-base --is-ancestor <ref> develop`, `git cat-file -e
<ref>:<path>`, `ls` for a draft asserted to be missing -- and either confirm it
or rewrite it in the past tense with the verification named. A status doc is the
first thing the next session trusts, so a stale one costs more than stale prose
anywhere else.

Two of the six contradicted their own paragraph (a "nothing pushed" note about a
commit that had shipped), which is what long append-only entries produce: correct
the whole entry, not the sentence you arrived at.
