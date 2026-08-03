#!/usr/bin/env python3
"""Resolve individual conflict hunks in a merge-conflicted file.

Usage:  resolve_hunks.py <file> <spec>
        spec = comma-separated per-hunk choices, 1-based, in hunk order.
               'o' = keep our side, 't' = keep their side.
               e.g. "o,t,o" for a 3-hunk file.

Refuses to write unless the spec length matches the hunk count exactly -- a
short spec silently dropping the tail is the failure mode worth preventing,
since the result would still look resolved.
"""
from __future__ import annotations

import pathlib
import re
import sys

HUNK = re.compile(
    r"^<<<<<<< [^\n]*\n(?P<ours>.*?)^=======\n(?P<theirs>.*?)^>>>>>>> [^\n]*\n",
    re.S | re.M,
)


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    path = pathlib.Path(sys.argv[1])
    spec = [s.strip().lower() for s in sys.argv[2].split(",") if s.strip()]
    text = path.read_text(errors="surrogateescape")

    hunks = list(HUNK.finditer(text))
    if len(hunks) != len(spec):
        print(f"REFUSED: {path} has {len(hunks)} hunks, spec has {len(spec)}")
        return 1
    if any(c not in ("o", "t") for c in spec):
        print("REFUSED: spec entries must be 'o' or 't'")
        return 1

    out, last = [], 0
    for m, choice in zip(hunks, spec):
        out.append(text[last : m.start()])
        out.append(m.group("ours") if choice == "o" else m.group("theirs"))
        last = m.end()
    out.append(text[last:])
    result = "".join(out)

    if "<<<<<<< " in result or ">>>>>>> " in result:
        print(f"REFUSED: {path} would still contain conflict markers")
        return 1

    path.write_text(result, errors="surrogateescape")
    print(f"resolved {path}: {''.join(spec)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
