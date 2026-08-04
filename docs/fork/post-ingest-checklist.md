# Post-Ingest Checklist

Run this after an upstream ingest merge lands on `develop`. Fork-only.

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

Rollbacks land at `refs/prerebase/<branch>`. **Push them** — a rollback that only
exists locally is not a rollback.

## 2. Verify no work was lost

```bash
git range-diff <old-base>..origin/<branch> upstream-mirror..<branch>
```

Read the branch's OWN commits: `=` unchanged, `!` changed by conflict
resolution, `<` only in the old series. On a stale branch the `<` list is mostly
inherited upstream commits, not losses.

Do **not** diff added-line sets against the current mirror. A pre-rebase branch
was built on the old mirror, so every upstream commit since reads as a "loss" —
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
— the same function hardened against ReDoS that week. That is a risk ranking for
what to test hardest next, and it cost 15 seconds.

Three things that make the difference between a finding and a false finding:

- **`.graphifyignore` must exist before the build.** It is committed, so a fresh
  clone is fine. `venv/` alone was 29,830 of this repo's 31,594 py/js files (94%)
  — unfiltered, the ranking is dependency internals. Editing it requires deleting
  `graphify-out/`, not just `update`: exclusions apply on a fresh build only.
- **Verify by node count, not exit status.** `update` silently refuses a rebuild
  yielding fewer nodes than the last one, so an ignore-file edit can look applied
  while you query the old graph.
- **A zero in the coverage check may mean the convention differs.**
  `_buildEditor()` (82 edges) showed zero test files; six editor test files exist
  and assert `galleryEditor.js` by source text rather than naming the symbol.
  Read the tests before reporting a zero.

Then hand each hub you care about to the semantic index
(`mcp__serena__find_referencing_symbols`) for its **caller set**. The graph ranks
and cannot say who calls what; the index returns callers and cannot rank. Act on
the caller set, never on the degree count — a high degree says a symbol matters,
not what it does.

## 7. Full suite, and check what it leaked

```bash
before=$(ls -1U /tmp | grep -c '^tmp.*\.db$')
DATABASE_URL=sqlite:///:memory: venv/bin/python -m pytest tests/ -q --ignore=tests/bench
after=$(ls -1U /tmp | grep -c '^tmp.*\.db$')
echo "leaked: $((after-before))"
```

`/tmp` is a RAM-backed tmpfs on this machine. When it filled, 10 Playwright tests
failed with `Page.goto: Page crashed` and `ERROR at setup` — indistinguishable
from a code regression, and two of them were the tests whose job is catching a bad
merge resolution. Before blaming a Playwright failure on the diff, run
`df -h /tmp` and check for orphaned `/tmp/.org.chromium.Chromium.*` files from
crashed browsers.

---

## Record the result

Update `docs/fork/upstream/pr-status.md` with the rebase state, any supersessions
found, and the branches whose status changed. That document is what PRs are filed
from; an ingest that does not update it leaves the next filing pass working from
a stale map.
