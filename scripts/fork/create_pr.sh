#!/usr/bin/env bash
# create_pr.sh – Fork automation helper
# Opens a GitHub Pull Request for the given branch, using the corresponding PR draft.
# Usage: ./scripts/fork/create_pr.sh <branch-name>

set -euo pipefail

BRANCH="${1:-}"
if [[ -z "$BRANCH" ]]; then
  echo "Error: branch name required"
  exit 1
fi

# Determine absolute repo root
REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

# Ensure branch exists locally
if ! git rev-parse --verify "$BRANCH" >/dev/null 2>&1; then
  echo "Error: branch '$BRANCH' does not exist"
  exit 1
fi

# Find matching PR draft file (case‑insensitive match on branch name)
DRAFT_PATH=$(find "$REPO_ROOT/docs/fork/upstream/pr-drafts" -type f -iname "*${BRANCH#*/}*.md" | head -n 1 || true)
if [[ -z "$DRAFT_PATH" ]]; then
  echo "Error: No PR draft found for branch '$BRANCH' in docs/fork/upstream/pr-drafts"
  exit 1
fi

# Extract title and body from draft (first line after '---' is title, rest is body)
TITLE=$(grep -m1 -A0 '^---' -A1 "$DRAFT_PATH" | tail -n1 | sed 's/^\s*//')
BODY=$(sed '1,/^---$/d' "$DRAFT_PATH")

# Create PR via gh CLI, targeting the fork's dev branch (as per fork policy)
# Adjust base branch name if your workflow uses a different one.

gh pr create \
  --title "$TITLE" \
  --body "$BODY" \
  --head "$BRANCH" \
  --base dev

echo "Pull request created for branch $BRANCH"
