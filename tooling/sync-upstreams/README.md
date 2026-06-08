# Upstream Ingest Pipeline

Keeps this fork current with `upstream/dev` through a verified, gate-checked pipeline.
Full workflow documentation: `docs/dev/git-branch-workflow.md`.

## Quick reference

```bash
# Must be on integration branch first
git checkout integration

# Standard sync (requires venv for pytest gate)
python3 tooling/sync-upstreams/upstream_ingest_pipeline.py

# Skip pytest (CI mode or no venv)
python3 tooling/sync-upstreams/upstream_ingest_pipeline.py --skip-tests

# Dry run — gates only, no commits
python3 tooling/sync-upstreams/upstream_ingest_pipeline.py --dry-run

# Sync and push integration + tags to origin
python3 tooling/sync-upstreams/upstream_ingest_pipeline.py --skip-tests --push
```

After a successful sync, promote to develop manually:

```bash
git checkout develop && git merge integration && git push origin develop
```

## What it does

```
upstream/dev
    ↓  fetch + reset upstream-mirror
sync/staging-TIMESTAMP
    ↓  Gate 1: Python syntax check
    ↓  Gate 2: ruff lint (warn-only)
    ↓  Gate 3: pytest smoke tests
integration  [ff-only merge + LKG-TIMESTAMP tag]
```

## Protected files

After each merge, the pipeline restores fork-owned files to their `integration` state so upstream can't overwrite them. Currently protected:

- `tooling/sync-upstreams/upstream_ingest_pipeline.py` — the pipeline itself
- `.github/workflows/sync-upstream.yml` — fork-only CI workflow
- `.env.example` — may have fork-specific env vars
- `README.md` — fork uses `assets/` paths, upstream uses `docs/`

Add new fork-specific files to `PROTECTED_FILES` at the top of the script.

## assets/ media cleanup

This fork moved upstream's media files from `docs/` to `assets/`. After each merge, the pipeline scans the top level of `docs/` and removes any media file (`.gif .webm .jpg .jpeg .png .svg .webp`) that has a canonical copy in `assets/`. Upstream re-adding these files to `docs/` is handled automatically. If upstream adds a new media format, add its extension to `_MOVED_TO_ASSETS_EXTS` in the pipeline source.

## Merge conflicts

If the merge into the staging branch fails with a conflict, the pipeline aborts and cleans up. Resolve manually:

```bash
# Create a staging branch by hand
git checkout integration
git checkout -b sync/staging-manual
git merge upstream-mirror   # will fail — shows conflicting files
# Resolve each file: for fork-owned files, keep integration's version
git add <resolved files>
git commit -m "chore(sync): resolve merge conflict with upstream"

# Run gates by hand
python3 tooling/sync-upstreams/upstream_ingest_pipeline.py --dry-run

# Promote manually
git checkout integration
git merge --ff-only sync/staging-manual
git tag -a LKG-MANUAL -m "Last Known Good — manual conflict resolution"
git branch -D sync/staging-manual
git push origin integration --follow-tags
```

## CI

`.github/workflows/sync-upstream.yml` runs daily at 3am UTC with `--skip-tests --push`. Check `origin/integration` after that to see if new commits landed.
