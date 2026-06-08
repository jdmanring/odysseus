# Git Branch Workflow

## Branch Map

| Branch | Purpose |
|--------|---------|
| `upstream-mirror` | Reset to `upstream/dev` on every sync — **never commit here** |
| `integration` | Vetted upstream changes that passed all pipeline gates |
| `develop` | Active fork development — primary working branch |
| `main` | Stable release of the fork |
| `feat/*` / `fix/*` | Feature and fix branches — merge to `develop` when complete |

Upstream has its own two-branch model: `dev` (all PRs land here) and `main` (stable).
All upstream PRs target `upstream:dev`, never `upstream:main`.

## Syncing Upstream Changes

**Never cherry-pick from upstream directly to `develop`.** Use the pipeline:

```
tooling/sync-upstreams/upstream_ingest_pipeline.py
```

The pipeline runs 3 gates before promoting to `integration`:
1. Syntax check
2. Lint
3. Tests

Once on `integration`, merge to `develop` normally.

## Remotes

```
origin    → github.com/jdmanring/odysseus       (James's fork — normal dev target)
upstream  → github.com/pewdiepie-archdaemon/odysseus  (source — read-only, no push)
```

## Hard Rules

- Never push to `upstream` remote
- Never commit to `upstream-mirror`
- Never cherry-pick upstream → `develop` directly (always pipeline via `integration`)
- Never file issues or PRs on upstream without James's explicit per-action authorization
