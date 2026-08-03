#!/usr/bin/env python3
"""Did a rebase KEEP the branch's own work?

Passing a branch's own tests is weaker than it looks: a test suite asserts the
properties someone thought to write down, and a rebase conflict resolution can
silently drop a line no test names. The direct question is whether the lines the
branch ADDED before the rebase are still added after it.

Method, per branch:
  before = diff(old_mirror .. refs/prerebase/<branch>)   the branch's original patch
  after  = diff(upstream-mirror .. <branch>)             the branch's patch now
Report lines that `before` ADDS and `after` does not.

A hit is a CANDIDATE, not a defect. Legitimate causes:
  * upstream already shipped the same line, so the rebase correctly dropped it
  * the line was deliberately superseded during conflict resolution
  * a rename or reindent changed the text
Short and boilerplate lines are skipped because they collide across unrelated code.

Usage:
    verify_rebase.py --old-mirror <ref> [branch...]
"""
from __future__ import annotations

import subprocess
import sys

MIN_LEN = 24
BOILERPLATE = ("import ", "from ", "}", "{", "});", "});\n", "return", "else:", "try:")


def sh(*a: str) -> str:
    return subprocess.run(a, capture_output=True, text=True).stdout


def added(diff: str) -> list[str]:
    out = []
    for line in diff.splitlines():
        if not line.startswith("+") or line.startswith("+++"):
            continue
        s = line[1:].strip()
        if len(s) < MIN_LEN or s.startswith(BOILERPLATE):
            continue
        out.append(s)
    return out


def main() -> int:
    argv = sys.argv[1:]
    if "--old-mirror" not in argv:
        print(__doc__)
        return 2
    old = sh("git", "rev-parse", argv[argv.index("--old-mirror") + 1]).strip()
    branches = [a for a in argv if not a.startswith("-")][1:]
    if not branches:
        branches = [r.split("refs/prerebase/", 1)[1] for r in
                    sh("git", "for-each-ref", "--format=%(refname)", "refs/prerebase/").split()]

    flagged = 0
    for br in branches:
        pre = f"refs/prerebase/{br}"
        if not sh("git", "rev-parse", "--verify", "--quiet", pre).strip():
            continue
        before = added(sh("git", "diff", f"{old}...{pre}"))
        after = set(added(sh("git", "diff", f"upstream-mirror...{br}")))
        if not before:
            continue
        lost = [l for l in before if l not in after]
        if not lost:
            print(f"  {br:<44} OK  ({len(before)} added lines all present)")
            continue
        flagged += 1
        print(f"\n  {br}  — {len(lost)} of {len(before)} added lines NOT in the rebased patch")
        for l in lost[:6]:
            print(f"      {l[:100]}")
        if len(lost) > 6:
            print(f"      ... and {len(lost)-6} more")

    print(f"\n{'='*70}\n{flagged} branch(es) with lines to review.")
    print("CANDIDATES: upstream may already ship the line, or it was deliberately")
    print("superseded. Read the branch before concluding anything was lost.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
