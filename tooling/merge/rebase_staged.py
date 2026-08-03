#!/usr/bin/env python3
"""Rebase staged contribution branches onto the new upstream-mirror after an ingest.

THE TRAP THIS EXISTS TO AVOID
-----------------------------
`upstream-mirror` is RESET (force-moved) by the sync pipeline, not fast-forwarded.
So after an ingest the old fork point is no longer an ancestor of the new mirror,
and `git merge-base <branch> upstream-mirror` returns some ancient commit. Rebasing
onto that base replays ~1,900 commits per branch and conflicts immediately.

The correct base is the OLD upstream-mirror -- the tag taken before the ingest.
Measured on this repo: with merge-base, a 2-commit branch tried to replay 1,923
commits and conflicted; with the old-mirror tag, the same branch rebased clean.
Always pass --old-mirror explicitly; there is no safe way to infer it.

SAFETY
------
Every branch's pre-rebase tip is saved to `refs/prerebase/<branch>` before it is
touched, so any branch can be restored with:
    git update-ref refs/heads/<branch> refs/prerebase/<branch>
A branch is moved ONLY if its rebase completes cleanly. Conflicted rebases are
aborted and reported; nothing is auto-resolved, because a resolution nobody read
is how fork work gets silently dropped.

Usage:
    rebase_staged.py --old-mirror <ref> [--apply] [branch...]

Without --apply it is a DRY RUN: it reports what would rebase clean and what
would conflict, and moves no refs.
"""
from __future__ import annotations

import subprocess
import sys


# A staged single-fix PR branch never carries this many commits since the
# mirror; anything above it is a develop-based fork-only branch.
FORK_ONLY_THRESHOLD = 50


def sh(*a: str, cwd: str | None = None) -> tuple[int, str]:
    p = subprocess.run(a, capture_output=True, text=True, cwd=cwd)
    return p.returncode, p.stdout + p.stderr


def main() -> int:
    argv = sys.argv[1:]
    if "--old-mirror" not in argv:
        print(__doc__)
        return 2
    i = argv.index("--old-mirror")
    old_mirror = argv[i + 1]
    apply = "--apply" in argv
    branches = [a for a in argv if not a.startswith("-") and a != old_mirror]

    rc, old_sha = sh("git", "rev-parse", old_mirror)
    if rc != 0:
        print(f"cannot resolve --old-mirror {old_mirror!r}")
        return 2
    old_sha = old_sha.strip()

    if not branches:
        _, out = sh("git", "branch", "--format=%(refname:short)")
        branches = [
            b for b in out.split()
            if b not in {"develop", "integration", "upstream-mirror", "main"}
            and not b.startswith(("backup/", "bench/", "sync/"))
        ]

    # A dedicated worktree keeps the caller's checkout untouched.
    import tempfile
    wt = tempfile.mkdtemp(prefix="rebase-staged-")
    rc, out = sh("git", "worktree", "add", "-q", "--detach", wt, "upstream-mirror")
    if rc != 0:
        print("could not create worktree:", out)
        return 1

    clean, conflict, empty, skipped = [], [], [], []
    try:
        for b in branches:
            # IDEMPOTENCE FIRST. Once a branch has been rebased its base IS the
            # current mirror, so `old_mirror..branch` becomes the whole new
            # upstream history (~1,950 commits) and every size heuristic below
            # would misread it as a huge develop-based branch. Ask the direct
            # question instead: is the current mirror already an ancestor?
            rc_anc, _ = sh("git", "merge-base", "--is-ancestor", "upstream-mirror", b)
            if rc_anc == 0:
                n = len(sh("git", "rev-list", f"upstream-mirror..{b}")[1].split())
                skipped.append((b, f"already on the current mirror ({n} own commit(s))"))
                continue

            rc, out = sh("git", "rev-list", "--count", f"{old_sha}..{b}")
            own = int(out.strip() or 0) if rc == 0 else -1
            if own <= 0:
                skipped.append((b, "no commits since the old mirror"))
                continue

            # FORK-ONLY branches are cut from `develop`, not `upstream-mirror`
            # (CLAUDE.md: sync pipeline, fork CI, fork management docs). Rebasing
            # one onto the mirror replays the fork's whole divergence and conflicts
            # on the pipeline file every time. They are separable by size: a staged
            # single-fix PR branch carries a handful of commits since the mirror,
            # while a develop-based branch carries hundreds. Measured here BEFORE
            # any rebase: upstream-candidate branches ranged 1-38, the seven
            # fork-only ones 58-1230, with no overlap. This test is only valid on
            # a not-yet-rebased branch, which the ancestor check above guarantees.
            _, fd = sh("git", "rev-list", "--count", f"develop..{b}")
            from_develop = int(fd.strip() or 0)
            if own > FORK_ONLY_THRESHOLD and from_develop < own:
                skipped.append((
                    b, f"looks FORK-ONLY (develop-based): {own} commits since the "
                       f"mirror but only {from_develop} not on develop — rebase onto "
                       f"develop instead, never onto upstream-mirror"))
                continue

            sh("git", "checkout", "-q", "-B", "_rb", b, cwd=wt)
            rc, out = sh("git", "rebase", "--onto", "upstream-mirror", old_sha, "_rb", cwd=wt)
            if rc != 0:
                _, u = sh("git", "diff", "--name-only", "--diff-filter=U", cwd=wt)
                conflict.append((b, own, sorted(set(u.split()))))
                sh("git", "rebase", "--abort", cwd=wt)
                continue

            _, cnt = sh("git", "rev-list", "--count", "upstream-mirror.._rb", cwd=wt)
            n = int(cnt.strip() or 0)
            if n == 0:
                empty.append((b, own))
                continue
            if apply:
                _, tip = sh("git", "rev-parse", b)
                sh("git", "update-ref", f"refs/prerebase/{b}", tip.strip())
                _, new = sh("git", "rev-parse", "_rb", cwd=wt)
                sh("git", "update-ref", f"refs/heads/{b}", new.strip())
            clean.append((b, own, n))
    finally:
        sh("git", "worktree", "remove", "--force", wt)
        # `-B _rb` creates a real branch ref; without this it survives the
        # worktree and shows up in `git branch` as mystery junk.
        sh("git", "branch", "-D", "_rb")

    mode = "APPLIED" if apply else "DRY RUN (no refs moved)"
    print(f"=== {mode} — base {old_mirror} ({old_sha[:8]}) ===\n")
    print(f"CLEAN ({len(clean)}):")
    for b, own, n in clean:
        note = "" if n == own else f"  [{own} -> {n}: {own - n} already upstream]"
        print(f"  {b:<46} {n} commit(s){note}")
    if empty:
        print(f"\nEMPTY AFTER REBASE ({len(empty)}) — upstream shipped every commit; retire these:")
        for b, own in empty:
            print(f"  {b:<46} was {own}")
    if conflict:
        print(f"\nCONFLICT ({len(conflict)}) — aborted, nothing auto-resolved:")
        for b, own, files in conflict:
            print(f"  {b:<46} {own} commit(s) -> {' '.join(files[:4])}")
    if skipped:
        print(f"\nSKIPPED ({len(skipped)}):")
        for b, why in skipped:
            print(f"  {b:<46} {why}")

    if apply and clean:
        print("\nRollback any branch with:")
        print("  git update-ref refs/heads/<branch> refs/prerebase/<branch>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
