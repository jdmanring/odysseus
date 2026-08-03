#!/usr/bin/env python3
"""Classify each conflict hunk by WHO MOVED LAST, from history rather than looks.

Why this exists
---------------
Twice in this merge I inferred authorship from how content read, and twice I was
wrong in the same direction: our side held the upstream author's own machine
hostnames (upstream had deliberately scrubbed them) and a dead function upstream
had deleted. In a long-lived fork with duplicate history, MOST of "ours" is stale
upstream, so "this looks fork-specific" is weak evidence.

The mechanical test, per hunk:
  * content on OUR side that also exists in the MERGE BASE  -> upstream wrote it
    and upstream later removed it. Ours is STALE. Theirs wins.
  * content on OUR side ABSENT from the merge base          -> the fork authored
    it after the base. Genuinely ours.

Same logic mirrored for their side, which distinguishes an upstream ADDITION from
an upstream REVERT.

Output is advisory: it prints a suggested spec but decides nothing. Hunks it
cannot classify are marked REVIEW, and those still have to be read.

Usage: classify_hunks.py <file>
"""
from __future__ import annotations

import re
import subprocess
import sys
import pathlib

HUNK = re.compile(
    r"^<<<<<<< [^\n]*\n(?P<o>.*?)^=======\n(?P<t>.*?)^>>>>>>> [^\n]*\n", re.S | re.M)


def sh(*a: str) -> str:
    return subprocess.run(a, capture_output=True, text=True).stdout


def significant(block: str) -> list[str]:
    """Lines worth testing: long enough that a base match is not coincidence."""
    return [l.strip() for l in block.splitlines() if len(l.strip()) > 25]


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    f = sys.argv[1]
    base = sh("git", "merge-base", "develop", "upstream-mirror").strip()
    base_lines = {l.strip() for l in sh("git", "show", f"{base}:{f}").splitlines()}
    if not base_lines:
        print(f"{f}: not in merge base — every hunk is new on both sides, REVIEW all")
        return 0

    text = pathlib.Path(f).read_text(errors="surrogateescape")
    spec, notes = [], []
    for i, m in enumerate(HUNK.finditer(text), 1):
        o, t = m.group("o"), m.group("t")
        os_, ts_ = significant(o), significant(t)
        o_in_base = sum(1 for l in os_ if l in base_lines)
        t_in_base = sum(1 for l in ts_ if l in base_lines)

        if not ts_ and os_:                      # ours-only
            if o_in_base == len(os_):
                spec.append("t"); notes.append(f"{i}: t  ours-only but ALL {len(os_)} lines in base -> STALE, upstream deleted it")
            elif o_in_base == 0:
                spec.append("o"); notes.append(f"{i}: o  ours-only, none in base -> fork-authored")
            else:
                spec.append("?"); notes.append(f"{i}: ?  ours-only, {o_in_base}/{len(os_)} in base -> REVIEW")
        elif not os_ and ts_:                    # theirs-only
            if t_in_base == 0:
                spec.append("t"); notes.append(f"{i}: t  theirs-only, none in base -> upstream addition")
            else:
                spec.append("?"); notes.append(f"{i}: ?  theirs-only, {t_in_base}/{len(ts_)} in base -> REVIEW (upstream revert?)")
        else:                                    # both sides
            if os_ and o_in_base == len(os_) and t_in_base < len(ts_):
                spec.append("t"); notes.append(f"{i}: t  ours all-in-base, theirs has new content -> upstream moved last")
            elif ts_ and t_in_base == len(ts_) and o_in_base < len(os_):
                spec.append("o"); notes.append(f"{i}: o  theirs all-in-base, ours has new content -> fork moved last")
            else:
                # "Both changed" lumps together two situations that need OPPOSITE
                # handling, and calling them all REVIEW hid that. Compare each
                # side's UNIQUE lines against the base:
                #   both sides have unique non-base lines -> both ADDED different
                #     things here. Neither supersedes the other and choosing either
                #     side silently drops a feature. This must be a UNION/port.
                #   only one side does -> that side moved last.
                # Measured on static/style.css, where several hunks had the fork
                # adding theme rules while upstream added an unrelated widget at
                # the same offset. A plain o/t choice loses one of them.
                o_new = [l for l in set(os_) - set(ts_) if l not in base_lines]
                t_new = [l for l in set(ts_) - set(os_) if l not in base_lines]
                if o_new and t_new:
                    # KNOWN FALSE POSITIVE, common in CSS: when one side merely
                    # EXTENDS a selector list, the line changes from `X {` to
                    # `X,` + `Y {`, so a line-level diff sees unique lines on both
                    # sides while that side is a strict superset. Read the hunk: if
                    # one side's selectors contain all of the other's, take it
                    # rather than porting. Measured on static/style.css hunks
                    # 8/9/10/13/18/25.
                    spec.append("?"); notes.append(
                        f"{i}: ?  UNION — both sides added non-base content "
                        f"(fork {len(o_new)}, upstream {len(t_new)}); porting required, o/t drops one"
                        " [check first for a selector-list superset]")
                elif o_new:
                    spec.append("o"); notes.append(f"{i}: o  only ours has non-base content -> fork moved last")
                elif t_new:
                    spec.append("t"); notes.append(f"{i}: t  only theirs has non-base content -> upstream moved last")
                else:
                    spec.append("?"); notes.append(f"{i}: ?  both changed, neither adds non-base content -> REVIEW")

    print(f"{f}: {len(spec)} hunks")
    for n in notes:
        print("   ", n)
    print("\n  suggested spec:", ",".join(spec))
    print(f"  REVIEW needed: {spec.count('?')} of {len(spec)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
