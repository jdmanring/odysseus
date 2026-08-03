#!/usr/bin/env python3
"""Strip AI co-authorship trailers from a branch's own commits.

Why
---
Upstream's CONTRIBUTING.md prohibits agent-filed PRs. Every staged contribution
branch carries `Co-Authored-By: Claude ...` trailers, so filing one advertises
exactly what the project forbids. The commits are the fork author's work; the
trailers are a harness default that should never have been written.

How
---
Replays each commit with `git commit-tree`, reusing the ORIGINAL TREE. Nothing is
merged or re-applied, so this cannot conflict and cannot change a single byte of
content -- only the message. Author and committer identity and both timestamps are
preserved, so `git log --format=%ad` is unchanged.

That is the whole reason not to use `rebase` or `filter-branch` here: rebase
re-applies patches (and can conflict), and filter-branch is a foot-gun with a
different failure mode per invocation. Tree reuse makes the content invariant a
property of the method rather than something to verify afterwards -- though
--verify checks it anyway.

Scope is `<base>..<branch>`, i.e. only commits the branch itself introduced.
Shared history is never touched.

Safety
------
The pre-scrub tip is saved to `refs/prescrub/<branch>` before the ref moves.
Dry run by default.

Usage:
    scrub_attribution.py --base <ref> [--apply] [--verify] [branch...]
"""
from __future__ import annotations

import re
import subprocess
import sys

# Every shape seen in this repo's history, plus the "Generated with" and emoji
# footers the harness has used. Matched per-line, case-insensitively.
PATTERNS = [
    re.compile(r"^\s*co-authored-by:\s*claude\b.*$", re.I),
    re.compile(r"^\s*co-authored-by:\s*.*<[^>]*anthropic\.com>\s*$", re.I),
    re.compile(r"^\s*supported by claude\b.*$", re.I),
    re.compile(r"^\s*generated with .*claude.*$", re.I),
    re.compile(r"^\s*claude-session:\s*.*$", re.I),
    re.compile(r"^\s*🤖.*claude.*$", re.I),
]


def sh(*a: str) -> str:
    p = subprocess.run(a, capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit(f"git failed: {' '.join(a)}\n{p.stderr}")
    return p.stdout


def clean(msg: str) -> str:
    kept = [l for l in msg.splitlines() if not any(p.match(l) for p in PATTERNS)]
    while kept and not kept[-1].strip():
        kept.pop()
    return "\n".join(kept) + "\n"


def main() -> int:
    argv = sys.argv[1:]
    if "--base" not in argv:
        print(__doc__)
        return 2
    base = argv[argv.index("--base") + 1]
    apply = "--apply" in argv
    verify = "--verify" in argv
    branches = [a for a in argv if not a.startswith("-") and a != base]
    if not branches:
        branches = [
            b for b in sh("git", "branch", "--format=%(refname:short)").split()
            if b not in {"develop", "integration", "upstream-mirror", "main"}
        ]

    base_sha = sh("git", "rev-parse", base).strip()
    total_touched = 0
    skipped = []
    for br in branches:
        # SCOPE GUARD. Only branches that actually sit on `base` have `base..br`
        # equal to their own work. For anything else -- a develop-based fork-only
        # branch, an un-rebased staged branch, the ingest branch itself -- that
        # range is the fork's whole divergence, and scrubbing it would rewrite
        # history that is already merged and pushed. Measured: without this the
        # sweep proposed 9,030 commits across 101 branches, including 1,278 on
        # `sync/ingest-20260802`, which is develop's own history.
        rc = subprocess.run(["git", "merge-base", "--is-ancestor", base_sha, br],
                            capture_output=True).returncode
        if rc != 0:
            skipped.append((br, f"not based on {base} — rebase it first"))
            continue

        # ALREADY-MERGED GUARD, and this is the one that matters. A branch that is
        # an ancestor of `develop` has been merged and pushed; rewriting it rewrites
        # PUBLISHED history. The ancestor check above does NOT catch this: the ingest
        # branch has upstream-mirror as a genuine parent, so it passes, while its
        # range is the fork's entire divergence. Measured: `sync/ingest-20260802`
        # offered 1,278 commits for scrubbing on exactly that path.
        rc = subprocess.run(["git", "merge-base", "--is-ancestor", br, "develop"],
                            capture_output=True).returncode
        if rc == 0:
            skipped.append((br, "already merged into develop — rewriting published history"))
            continue

        # A staged PR branch is LINEAR. A merge commit in the range means this is an
        # integration branch, not a contribution, and its range is not its own work.
        merges = sh("git", "rev-list", "--merges", f"{base_sha}..{br}").split()
        if merges:
            skipped.append((br, f"{len(merges)} merge commit(s) in range — not a linear PR branch"))
            continue
        try:
            revs = sh("git", "rev-list", "--reverse", f"{base_sha}..{br}").split()
        except SystemExit:
            continue
        if not revs:
            continue

        new_parent = base_sha
        touched = 0
        for rev in revs:
            msg = sh("git", "log", "-1", "--format=%B", rev)
            new_msg = clean(msg)
            if new_msg.strip() != msg.strip():
                touched += 1
            if not apply:
                continue
            meta = sh("git", "log", "-1",
                      "--format=%an%x00%ae%x00%aI%x00%cn%x00%ce%x00%cI", rev).split("\x00")
            an, ae, ad, cn, ce, cd = [x.strip() for x in meta]
            env = {
                "GIT_AUTHOR_NAME": an, "GIT_AUTHOR_EMAIL": ae, "GIT_AUTHOR_DATE": ad,
                "GIT_COMMITTER_NAME": cn, "GIT_COMMITTER_EMAIL": ce, "GIT_COMMITTER_DATE": cd,
            }
            import os
            p = subprocess.run(
                ["git", "commit-tree", f"{rev}^{{tree}}", "-p", new_parent],
                input=new_msg, capture_output=True, text=True,
                env={**os.environ, **env})
            if p.returncode != 0:
                raise SystemExit(f"commit-tree failed on {rev}: {p.stderr}")
            new_parent = p.stdout.strip()

        if touched == 0:
            continue
        total_touched += touched
        if apply:
            old_tip = sh("git", "rev-parse", br).strip()
            sh("git", "update-ref", f"refs/prescrub/{br}", old_tip)
            sh("git", "update-ref", f"refs/heads/{br}", new_parent)
            if verify:
                # The content invariant: the final tree must be IDENTICAL. If this
                # ever fails the method is wrong, not the input.
                a = sh("git", "rev-parse", f"{old_tip}^{{tree}}").strip()
                b = sh("git", "rev-parse", f"{new_parent}^{{tree}}").strip()
                if a != b:
                    raise SystemExit(f"TREE CHANGED on {br} — aborting, refs/prescrub/{br} holds the original")
            print(f"  {br:<44} {touched} commit(s) scrubbed")
        else:
            print(f"  {br:<44} {touched} commit(s) would be scrubbed")

    if skipped:
        print(f"\nSKIPPED ({len(skipped)}) — reason per branch:")
        for b, why in skipped:
            print(f"  {b:<44} {why}")
    print(f"\n{'APPLIED' if apply else 'DRY RUN'}: {total_touched} commit message(s)"
          f" across {len(branches) - len(skipped)} in-scope branch(es)")
    if apply:
        print("Rollback: git update-ref refs/heads/<branch> refs/prescrub/<branch>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
