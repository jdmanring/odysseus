#!/usr/bin/env bash
# run_full_sync.sh – Fork automation helper
# Executes the full upstream‑sync pipeline:
#   1. Fetch latest upstream commits
#   2. Reset the upstream‑mirror branch
#   3. Fast‑forward develop to upstream‑mirror
#   4. Re‑base all open feature/fix branches onto the new develop
# Usage: ./scripts/fork/run_full_sync.sh

set -euo pipefail

# Ensure we are at the repository root
cd "$(git rev-parse --show-toplevel)"

# 1. Fetch upstream
git fetch upstream

# 2. Reset upstream‑mirror to upstream/dev
git checkout upstream-mirror
git reset --hard upstream/dev

# 3. Fast‑forward develop
git checkout develop
git merge --ff-only upstream-mirror

# 4. Re‑base open feature/fix branches onto develop
# Find local branches that are not develop or upstream‑mirror and have an upstream tracking branch
for branch in $(git branch --format='%(refname:short)' | grep -Ev '^(develop|upstream-mirror)$'); do
  echo "Re‑basing $branch onto develop"
  git checkout "$branch"
  git rebase develop
done

echo "Full sync completed successfully."
