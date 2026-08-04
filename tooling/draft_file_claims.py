#!/usr/bin/env python3
"""Does any PR draft name a source file that its branch does not contain?

The feat/logging draft listed src/log_timing.py as a new file after it was
dropped, and rested its "why one PR" argument on a caller that never existed. A
reviewer greps the first file they see. This checks every draft the same way.

Only flags paths the draft presents as its own (backticked, with a source-ish
extension) that are absent from the branch tip.

The two judgement calls -- which branch a draft claims, and which paths it
asserts as its own -- are pure functions so they can be tested without a repo.
See tests/test_draft_file_claims.py.
"""
import pathlib
import re
import subprocess
import sys

PATH_RE = re.compile(r"`([\w./-]+\.(?:py|js|mjs|css|sh|ps1|html|yml|yaml))`")
# Accept the three header spellings actually in use: **Branch:** ..., **Branch**: ...,
# and a bare Branch: ... . Requiring the colon inside the bold silently skipped 12
# real drafts, which then read as "0 problems".
BRANCH_RE = re.compile(r"^\*{0,2}Branch\*{0,2}\s*:\s*\*{0,2}\s*`([^`]+)`", re.M)
# A path used as the LINK TEXT of a markdown link to an explicit URL is a citation
# of where the file lives, not a claim that this branch holds it.
# fix-dom-oom-virtualization deliberately links its benchmark into the workbench
# and says in the same section that it is not in the PR.
LINKED_RE = re.compile(r"\[`([\w./-]+)`\]\(https?://")
# A path named in a proposal ("tests can be added in X") or in a correction note
# ("previously also listed X") is not a claim that the branch has it.
HEDGE = ("can be added", "could be added", "previously also listed",
         "was split out", "no dedicated test file", "if a test is wanted")


def branch_of(text: str) -> str | None:
    """The branch a draft claims, or None if it declares no header."""
    m = BRANCH_RE.search(text)
    return m.group(1) if m else None


# A hedge disqualifies the CLAUSE it sits in, not the whole line. Scoping it to
# the line dropped real claims that happened to share a line with a hedge --
# measured at 6 source paths across 2 drafts, silently reported as clean, which
# is the same "0 problems while blind" failure this module exists to prevent.
_CLAUSE_RE = re.compile(r"\([^()]*\)|[^;()]+|[;()]")


def _clauses(line: str) -> list[str]:
    """Split a line into parenthesised groups and semicolon-separated clauses."""
    return [c for c in _CLAUSE_RE.findall(line) if c.strip(" ;()")]


def asserted_paths(text: str) -> set[str]:
    """Paths the draft presents as its own, hedges and linked citations removed."""
    out: set[str] = set()
    for line in text.split("\n"):
        # Citations are matched on the whole line: a markdown link contains
        # parentheses, so clause-splitting would tear the URL off the path and
        # the citation would read as a claim.
        cited = set(LINKED_RE.findall(line))
        for clause in _clauses(line):
            if any(h in clause.lower() for h in HEDGE):
                continue
            out.update(p for p in PATH_RE.findall(clause) if p not in cited)
    return out


def main(root: pathlib.Path) -> int:
    drafts = root / "docs/fork/upstream/pr-drafts"

    def sh(*a):
        return subprocess.run(["git", "-C", str(root), *a],
                              capture_output=True).stdout.decode("utf-8", "replace")

    problems = 0
    checked = 0
    no_branch_header: list[str] = []
    retired = 0
    for d in sorted(drafts.glob("*.md")):
        text = d.read_text(encoding="utf-8")
        branch = branch_of(text)
        if branch is None:
            # Not an error -- some drafts predate the header convention -- but it
            # must be VISIBLE. "83 drafts, 0 problems" read as full coverage while
            # 16 of 99 had never been looked at, one of them edited that same day.
            no_branch_header.append(d.name)
            continue
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
        missing = sorted({p for p in asserted_paths(text)
                          if "/" in p and p not in tree and p.split("/")[0] in tops})
        if missing:
            print(f"  {d.name}  (branch {branch})")
            for p in missing:
                print(f"      names but branch lacks: {p}")
            problems += 1

    total = len(list(drafts.glob("*.md")))
    print(f"\nchecked {checked} of {total} drafts, {problems} with a problem")
    if retired:
        print(f"  {retired} skipped: branch retired/superseded and the draft says so")
    if no_branch_header:
        print(f"  {len(no_branch_header)} skipped: no Branch header, so nothing to check against")
        for n in no_branch_header:
            print(f"      {n}")
    return problems


if __name__ == "__main__":
    sys.exit(1 if main(pathlib.Path(sys.argv[1])) else 0)
