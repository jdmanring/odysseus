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
# Accept the three header spellings actually in use: **Branch:** ..., **Branch**: ...,
# and a bare Branch: ... . Requiring the colon inside the bold silently skipped 12
# real drafts, which then read as "0 problems".
BRANCH_RE = re.compile(r"^\*{0,2}Branch\*{0,2}\s*:\s*\*{0,2}\s*`([^`]+)`", re.M)


def sh(*a):
    return subprocess.run(["git", "-C", str(ROOT), *a],
                          capture_output=True).stdout.decode("utf-8", "replace")


problems = 0
checked = 0
no_branch_header: list[str] = []
retired = 0
for d in sorted(DRAFTS.glob("*.md")):
    text = d.read_text(encoding="utf-8")
    m = BRANCH_RE.search(text)
    if not m:
        # Not an error -- some drafts predate the header convention -- but it
        # must be VISIBLE. "83 drafts, 0 problems" read as full coverage while
        # 12 real drafts had never been looked at, one of them edited that same
        # day. A silent skip is worse than a reported gap.
        no_branch_header.append(d.name)
        continue
    branch = m.group(1)
    # A staged branch that is not checked out locally still exists on origin.
    # Resolving only the local name reported "DOES NOT EXIST" for three real
    # branches, which reads as lost work rather than a missing local ref.
    if not sh("rev-parse", "--verify", branch).strip():
        if sh("rev-parse", "--verify", f"origin/{branch}").strip():
            branch = f"origin/{branch}"
    if not sh("rev-parse", "--verify", branch).strip():
        # A retired branch is fine IF the draft says so. Silence is the defect.
        if "BRANCH RETIRED" in text or "SUPERSEDED (" in text:
            retired += 1
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
    # A path that is the LINK TEXT of a markdown link to an explicit URL is a
    # citation of where the file lives, not a claim that this branch holds it.
    # fix-dom-oom-virtualization deliberately links its benchmark into the
    # workbench and says in the same section that it is not in the PR.
    LINKED = re.compile(r"\[`([\w./-]+)`\]\(https?://")
    for line in text.split("\n"):
        if any(h in line.lower() for h in HEDGE):
            continue
        cited = set(LINKED.findall(line))
        asserted.update(p for p in PATH_RE.findall(line) if p not in cited)
    missing = sorted({p for p in asserted
                      if "/" in p and p not in tree and p.split("/")[0] in tops})
    if missing:
        print(f"  {d.name}  (branch {branch})")
        for p in missing:
            print(f"      names but branch lacks: {p}")
        problems += 1

total = len(list(DRAFTS.glob("*.md")))
print(f"\nchecked {checked} of {total} drafts, {problems} with a problem")
if retired:
    print(f"  {retired} skipped: branch retired/superseded and the draft says so")
if no_branch_header:
    print(f"  {len(no_branch_header)} skipped: no **Branch:** header, so nothing to check against")
    for n in no_branch_header:
        print(f"      {n}")
