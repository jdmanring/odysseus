#!/usr/bin/env python3
"""Does any PR draft name a source file that its branch does not contain?

The feat/logging draft listed src/log_timing.py as a new file after it was
dropped, and rested its "why one PR" argument on a caller that never existed. A
reviewer greps the first file they see. This checks every draft the same way.

Only flags paths the draft presents as its own (backticked, with a source-ish
extension) that are absent from the branch tip.
"""
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(sys.argv[1])
DRAFTS = ROOT / "docs/fork/upstream/pr-drafts"
PATH_RE = re.compile(r"`([\w./-]+\.(?:py|js|mjs|css|sh|ps1|html|yml|yaml))`")
BRANCH_RE = re.compile(r"^\*\*Branch:\*\*\s*`([^`]+)`", re.M)


def sh(*a):
    return subprocess.run(["git", "-C", str(ROOT), *a],
                          capture_output=True).stdout.decode("utf-8", "replace")


problems = 0
checked = 0
for d in sorted(DRAFTS.glob("*.md")):
    text = d.read_text(encoding="utf-8")
    m = BRANCH_RE.search(text)
    if not m:
        continue
    branch = m.group(1)
    if not sh("rev-parse", "--verify", branch).strip():
        # A retired branch is fine IF the draft says so. Silence is the defect.
        if "BRANCH RETIRED" in text or "SUPERSEDED (" in text:
            continue
        print(f"  {d.name}: branch {branch} DOES NOT EXIST and the draft does not say so")
        problems += 1
        continue
    checked += 1
    tree = set(sh("ls-tree", "-r", "--name-only", branch).split())
    # Only judge paths that CLAIM to be in this repo. A draft may legitimately
    # cite another repo's file (feat-memory-hybrid-recall cites the benchmark
    # suite's benchmark/hybrid_dense.py and says so); those live under a
    # top-level dir this repo does not have, so use that as the discriminator.
    tops = {p.split("/")[0] for p in tree}
    # A path named in a proposal ("tests can be added in X") or in a correction
    # note ("previously also listed X") is not a claim that the branch has it.
    # Judge only lines that assert.
    HEDGE = ("can be added", "could be added", "previously also listed",
             "was split out", "no dedicated test file", "if a test is wanted")
    asserted = set()
    for line in text.split("\n"):
        if any(h in line.lower() for h in HEDGE):
            continue
        asserted.update(PATH_RE.findall(line))
    missing = sorted({p for p in asserted
                      if "/" in p and p not in tree and p.split("/")[0] in tops})
    if missing:
        print(f"  {d.name}  (branch {branch})")
        for p in missing:
            print(f"      names but branch lacks: {p}")
        problems += 1

print(f"\nchecked {checked} drafts, {problems} with a problem")
