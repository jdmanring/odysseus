#!/usr/bin/env python3
"""Did the merge resolution DROP genuinely fork-authored work?

Why this exists
---------------
Resolving this merge I checked one direction only: whether I had KEPT stale
upstream content (content upstream deliberately deleted). That is the cosmetic
failure. The dangerous one is the inverse — fork work silently dropped by taking
"theirs" — and nothing was checking for it.

The test, per line of `develop`'s version of a file:
  * absent from upstream AND absent from the merge base  -> genuinely fork-authored
    (present in the base would mean it is old upstream text, not ours)
  * and missing from the merge result                     -> DROPPED

A hit is not automatically a bug: deliberately superseding fork code with an
upstream refactor drops fork lines on purpose. This tool finds candidates; a
human decides. It deliberately does not exit non-zero on findings.

Whitespace-only differences (a re-indented block) are the main false positive, so
every line is compared BOTH exactly and stripped, and only lines missing under
both comparisons are reported.

Usage:
    fork_work_loss.py               # every resolved file in the current merge
    fork_work_loss.py <file>...     # specific files
    fork_work_loss.py --upstream    # INVERSE: did we drop UPSTREAM work?

Run BOTH directions before calling a merge done. Dropping upstream work silently
reintroduces bugs they already fixed — this merge nearly kept a version regex that
made every Opus 5 call fail HTTP 400.
"""
from __future__ import annotations

import subprocess
import sys
import pathlib

MIN_LEN = 30          # short lines collide across unrelated code
SKIP_SUFFIX = (".png", ".jpg", ".jpeg", ".gif", ".ico", ".webm", ".pdf", ".lock")


def sh(*a: str) -> str:
    return subprocess.run(a, capture_output=True, text=True).stdout


def main() -> int:
    # --upstream inverts the question. Dropping UPSTREAM work is just as bad as
    # dropping ours: it silently reintroduces bugs they already fixed (this merge
    # nearly kept a regex that made every Opus 5 call fail HTTP 400). Same test,
    # mirrored: content on upstream, absent from develop AND the base, missing
    # from the merge result.
    upstream_mode = "--upstream" in sys.argv
    if upstream_mode:
        sys.argv.remove("--upstream")

    base = sh("git", "merge-base", "develop", "upstream-mirror").strip()
    if not base:
        print("no merge base — is upstream-mirror present?")
        return 0

    # Target discovery is the STAGED set. That is correct mid-merge (every merged
    # file is staged against HEAD) but silently yields NOTHING outside one — e.g.
    # after committing, or when a file's merged content happens to equal HEAD. Pass
    # paths explicitly when in doubt; an empty scan is not a clean scan.
    conflicted = set(sh("git", "diff", "--name-only", "--diff-filter=U").split())
    targets = sys.argv[1:] or [
        f for f in sh("git", "diff", "--cached", "--name-only").split()
        if f not in conflicted and not f.endswith(SKIP_SUFFIX)
    ]

    total_files, total_lines = 0, 0
    for f in targets:
        p = pathlib.Path(f)
        mine_ref, other_ref = ("upstream-mirror", "develop") if upstream_mode else ("develop", "upstream-mirror")
        dev = sh("git", "show", f"{mine_ref}:{f}")
        if not dev:
            continue                      # file absent on that side: nothing of theirs to lose
        up = sh("git", "show", f"{other_ref}:{f}")
        bs = sh("git", "show", f"{base}:{f}")
        cur = p.read_text(errors="replace") if p.is_file() else ""

        # RELOCATION AWARENESS: upstream moved route modules into subpackages and
        # left the old path as a shim, so `develop:routes/x_routes.py` (a full
        # module) compared against the merge's shim reports the WHOLE module as
        # lost. It is not — it moved. Fold the canonical file in as a second home.
        # Without this the tool reported 238 phantom lines across two files and
        # would have sent me re-porting code that was already there.
        stem = pathlib.Path(f).stem
        if f.startswith("routes/") and f.endswith("_routes.py") and "/" not in f[len("routes/"):]:
            canon = pathlib.Path("routes") / stem.removesuffix("_routes") / f"{stem}.py"
            if canon.is_file():
                cur += "\n" + canon.read_text(errors="replace")

        up_x, bs_x, cur_x = set(up.splitlines()), set(bs.splitlines()), set(cur.splitlines())
        up_s = {l.strip() for l in up_x}
        bs_s = {l.strip() for l in bs_x}
        cur_s = {l.strip() for l in cur_x}

        lost = []
        for l in dev.splitlines():
            s = l.strip()
            if len(s) < MIN_LEN:
                continue
            if l in up_x or s in up_s:      # upstream has it -> not ours to lose
                continue
            if l in bs_x or s in bs_s:      # in the base -> old upstream text, not fork-authored
                continue
            if l in cur_x or s in cur_s:    # survived (exact or re-indented)
                continue
            lost.append(s)
        if lost:
            total_files += 1
            total_lines += len(lost)
            label = "upstream-authored" if upstream_mode else "fork-authored"
            print(f"\n  {f}  ({len(lost)} {label} lines absent from the merge result)")
            for s in lost[:6]:
                print(f"      {s[:104]}")
            if len(lost) > 6:
                print(f"      ... and {len(lost)-6} more")

    print(f"\n{'='*70}")
    print(f"scanned {len(targets)} resolved files")
    side = "upstream" if upstream_mode else "fork"
    print(f"{total_files} files with dropped {side} lines, {total_lines} lines total")
    print("Each is a CANDIDATE: a deliberate supersession looks identical to a")
    print("mistake here. Read the surrounding hunk before concluding.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
