#!/usr/bin/env python3
"""Survey staged contribution branches after an upstream ingest.

Why this exists
---------------
After an ingest, every staged upstream-PR branch is based on the OLD
`upstream-mirror` and must be re-based onto the new one before it can be filed.
With ~86 tracked branches, rebasing blind is hours of conflicts, and most of the
work is usually a no-op: a branch whose commits are already on `develop` (they
were cherry-picked when it was cut) or already upstream (upstream shipped the
same fix) needs no rebase at all -- it needs retiring or a trivial replay.

SHA reachability cannot answer this: a cherry-picked commit has a different SHA.
Only patch-id can, which is what `git cherry` compares.

Per branch this reports:
  own      commits unique to the branch vs the OLD merge base
  !dev     of those, how many are NOT on develop by patch-id  (0 => fully landed)
  !up      of those, how many are NOT upstream by patch-id    (0 => upstream has it)
  verdict  RETIRE / LANDED / REBASE / EMPTY

Read-only. Runs no rebase, changes no ref. Verdicts are candidates.

Usage:
    branch_survey.py                 # every branch except backup/bench
    branch_survey.py <branch>...
"""
from __future__ import annotations

import subprocess
import sys


def sh(*a: str) -> str:
    return subprocess.run(a, capture_output=True, text=True).stdout


def cherry_unmerged(upstream_ref: str, branch: str, base: str) -> int:
    """Commits on `branch` since `base` whose patch-id is NOT in upstream_ref.

    `git cherry` prints '+' for commits with no equivalent upstream and '-' for
    ones already there. Counting '+' lines is the whole test.
    """
    out = sh("git", "cherry", upstream_ref, branch, base)
    return sum(1 for line in out.splitlines() if line.startswith("+"))


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args:
        branches = args
    else:
        branches = [
            b for b in sh("git", "branch", "--format=%(refname:short)").split()
            if b not in {"develop", "integration", "upstream-mirror", "main"}
            and not b.startswith(("backup/", "bench/"))
        ]

    rows = []
    for b in branches:
        base = sh("git", "merge-base", b, "upstream-mirror").strip()
        if not base:
            continue
        own = len(sh("git", "rev-list", f"{base}..{b}").split())
        if own == 0:
            rows.append((b, 0, 0, 0, "EMPTY"))
            continue
        not_dev = cherry_unmerged("develop", b, base)
        not_up = cherry_unmerged("upstream-mirror", b, base)
        if not_up == 0:
            verdict = "RETIRE"        # upstream already has every commit
        elif not_dev == 0:
            verdict = "LANDED"        # fully on develop; rebase only to file the PR
        else:
            verdict = "REBASE"        # genuinely unlanded work
        rows.append((b, own, not_dev, not_up, verdict))

    order = {"REBASE": 0, "LANDED": 1, "RETIRE": 2, "EMPTY": 3}
    rows.sort(key=lambda r: (order.get(r[4], 9), -r[2]))
    print(f"{'branch':<44} {'own':>5} {'!dev':>5} {'!up':>5}  verdict")
    for b, own, nd, nu, v in rows:
        print(f"{b:<44} {own:>5} {nd:>5} {nu:>5}  {v}")

    print()
    for v in ("REBASE", "LANDED", "RETIRE", "EMPTY"):
        n = sum(1 for r in rows if r[4] == v)
        print(f"  {v:<8} {n}")
    print("\nVerdicts are CANDIDATES. RETIRE means upstream shipped an equivalent")
    print("patch, which can also mean they shipped a WORSE one -- read before deleting.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
