#!/usr/bin/env bash
# post-merge-hook.sh – Fork automation helper
# Updates PR status tracking after a successful merge.
# Assumes the repository root contains docs/fork/upstream/pr-status.md.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

# The branch that was just merged is available via $GIT_MERGE_AUTOEDIT or via HEAD reflog.
# We'll use the most recent merge commit to infer the source branch name.
MERGED_BRANCH=$(git log -1 --pretty=%B | grep -Eo "Merge branch '([^']+)'" | cut -d"'" -f2 || true)
if [[ -z "$MERGED_BRANCH" ]]; then
  # Fallback: try to read from HEAD reflog
  MERGED_BRANCH=$(git reflog --date=iso | head -n1 | grep -Eo "merge\s+([^\ ]+)" | cut -d' ' -f2 || true)
fi

STATUS_FILE="docs/fork/upstream/pr-status.md"
if [[ -f "$STATUS_FILE" && -n "$MERGED_BRANCH" ]]; then
  # Mark the PR as Merged and remove the branch entry if present.
  # Simple approach: replace an existing line containing the branch name.
  sed -i.bak -E "s/^(\s*\-\s*\[.+\]\s*\|\s*)${MERGED_BRANCH}(.*)$/\1${MERGED_BRANCH} | Merged/" "$STATUS_FILE" || true
  # Optionally delete the branch entry line if a dedicated line exists.
  # This script is intentionally tolerant – it won't fail if patterns aren't found.
  echo "Updated PR status for merged branch $MERGED_BRANCH"
else
  echo "No PR status file or merged branch detected; nothing to update"
fi
