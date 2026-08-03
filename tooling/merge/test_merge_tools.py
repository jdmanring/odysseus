#!/usr/bin/env python3
"""Battery for the three merge tools.

These are the gate on a 182-file merge, so their failure modes matter more than
their features. Ordered by how badly a regression would hurt:

1. `resolve_hunks.py` must REFUSE rather than half-write. A spec that silently
   drops the tail of a file still LOOKS resolved, which is undetectable later.
2. `fork_work_loss.py` must not MISS a dropped line (a false negative is a
   silently lost feature) and must not drown real findings in false positives
   (which is how a reader learns to ignore it).
3. `classify_hunks.py` is advisory; wrong output costs a re-read, not data.

The two git-aware tools need a repo with `develop`, `upstream-mirror` and a real
merge base, so each test builds a throwaway one. Hermetic: nothing touches the
working repo.

Run: python3 tooling/merge/test_merge_tools.py
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).parent
RESOLVE = HERE / "resolve_hunks.py"
CLASSIFY = HERE / "classify_hunks.py"
LOSS = HERE / "fork_work_loss.py"
JSORPHAN = HERE / "js_orphan_refs.py"
REBASE = HERE / "rebase_staged.py"
SURVEY = HERE / "branch_survey.py"
SCRUB = HERE / "scrub_attribution.py"

CONFLICT = """common header
<<<<<<< HEAD
ours line one
=======
theirs line one
>>>>>>> upstream-mirror
middle text
<<<<<<< HEAD
ours line two
=======
theirs line two
>>>>>>> upstream-mirror
common footer
"""


def run(script: pathlib.Path, *args: str, cwd=None, env=None):
    p = subprocess.run([sys.executable, str(script), *args],
                       capture_output=True, text=True, timeout=120, cwd=cwd, env=env)
    return p.returncode, p.stdout + p.stderr


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)


def make_repo(tmp: str, base: str, dev: str, up: str, merged: str, path="f.py"):
    """A repo with a real merge base and two diverged branches.

    `merged` is written to the working tree and STAGED, standing in for a
    resolved-but-uncommitted merge, which is the state the tools inspect.
    """
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    subprocess.run(["git", "init", "-q", "-b", "develop", tmp], capture_output=True)
    f = pathlib.Path(tmp, path)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(base)
    subprocess.run(["git", "add", "-A"], cwd=tmp, capture_output=True, env=env)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=tmp, capture_output=True, env=env)
    subprocess.run(["git", "branch", "upstream-mirror"], cwd=tmp, capture_output=True, env=env)

    f.write_text(dev)
    subprocess.run(["git", "add", "-A"], cwd=tmp, capture_output=True, env=env)
    subprocess.run(["git", "commit", "-qm", "fork work"], cwd=tmp, capture_output=True, env=env)

    subprocess.run(["git", "checkout", "-q", "upstream-mirror"], cwd=tmp, capture_output=True, env=env)
    f.write_text(up)
    subprocess.run(["git", "add", "-A"], cwd=tmp, capture_output=True, env=env)
    subprocess.run(["git", "commit", "-qm", "upstream work"], cwd=tmp, capture_output=True, env=env)
    subprocess.run(["git", "checkout", "-q", "develop"], cwd=tmp, capture_output=True, env=env)

    f.write_text(merged)
    subprocess.run(["git", "add", "-A"], cwd=tmp, capture_output=True, env=env)
    return env


def main() -> int:
    fails: list[str] = []

    # ---------------- resolve_hunks: refusal is the load-bearing behaviour ----
    with tempfile.TemporaryDirectory() as t:
        f = pathlib.Path(t, "c.py"); f.write_text(CONFLICT)

        rc, out = run(RESOLVE, str(f), "o")                    # 1 choice, 2 hunks
        if rc == 0 or "REFUSED" not in out:
            fails.append("resolve: accepted a SHORT spec (silent tail-drop risk)")
        if f.read_text() != CONFLICT:
            fails.append("resolve: modified the file while refusing a short spec")

        rc, out = run(RESOLVE, str(f), "o,t,o")                # too many
        if rc == 0 or "REFUSED" not in out:
            fails.append("resolve: accepted an OVERLONG spec")

        rc, out = run(RESOLVE, str(f), "o,x")                  # bad token
        if rc == 0 or "REFUSED" not in out:
            fails.append("resolve: accepted an invalid spec token")
        if f.read_text() != CONFLICT:
            fails.append("resolve: modified the file on an invalid spec")

        rc, out = run(RESOLVE, str(f), "o,t")                  # valid
        got = f.read_text()
        if rc != 0:
            fails.append(f"resolve: valid spec failed: {out[:120]}")
        for must in ("common header", "ours line one", "theirs line two", "middle text", "common footer"):
            if must not in got:
                fails.append(f"resolve: lost {must!r}")
        if "ours line two" in got or "theirs line one" in got:
            fails.append("resolve: kept the UNCHOSEN side")
        if "<<<<<<<" in got or ">>>>>>>" in got or "=======" in got:
            fails.append("resolve: left conflict markers behind")

    # ---------------- resolve_hunks: union keeps BOTH sides ------------------
    with tempfile.TemporaryDirectory() as t:
        # Rebasing a staged fork branch onto a moved upstream produces add/add
        # hunks: upstream added bookkeeping where the fork added cleanup. Either
        # single-side choice silently drops a feature, so 'u' must keep both.
        f = pathlib.Path(t, "u.py"); f.write_text(CONFLICT)
        rc, out = run(RESOLVE, str(f), "u,u")
        got = f.read_text()
        if rc != 0:
            fails.append(f"resolve: union spec failed: {out[:120]}")
        for must in ("ours line one", "theirs line one", "ours line two", "theirs line two"):
            if must not in got:
                fails.append(f"resolve: union dropped {must!r}")
        # Guarded: if union is broken one side is ABSENT, and a bare .index()
        # would raise and abort the whole battery instead of reporting a failure.
        # A battery that dies mid-run silently skips every check after it.
        if "ours line one" in got and "theirs line one" in got:
            if got.index("ours line one") > got.index("theirs line one"):
                fails.append("resolve: union put THEIRS before OURS")
        if "<<<<<<<" in got or ">>>>>>>" in got:
            fails.append("resolve: union left conflict markers")

        f.write_text(CONFLICT)
        rc, out = run(RESOLVE, str(f), "u,x")
        if rc == 0 or "REFUSED" not in out:
            fails.append("resolve: accepted an invalid token alongside 'u'")

    # ---------------- fork_work_loss: false negatives are the danger ---------
    with tempfile.TemporaryDirectory() as t:
        # fork adds a line; merge result drops it => MUST be caught
        env = make_repo(t, "base line that is quite long indeed\n",
                        "base line that is quite long indeed\nfork only line long enough to count\n",
                        "base line that is quite long indeed\nupstream only line long enough here\n",
                        "base line that is quite long indeed\nupstream only line long enough here\n")
        rc, out = run(LOSS, cwd=t, env=env)
        if "fork only line" not in out:
            fails.append("loss: MISSED a genuinely dropped fork line (false negative)")
        # and the inverse direction must catch the upstream line when ours wins
        env = make_repo(t + "/x", "base line that is quite long indeed\n",
                        "base line that is quite long indeed\nfork only line long enough to count\n",
                        "base line that is quite long indeed\nupstream only line long enough here\n",
                        "base line that is quite long indeed\nfork only line long enough to count\n")
        # explicit target: when merged content equals develop HEAD nothing is
        # staged, so discovery finds no files. Real merges always stage.
        rc, out = run(LOSS, "--upstream", "f.py", cwd=t + "/x", env=env)
        if "upstream only line" not in out:
            fails.append("loss: --upstream MISSED a dropped upstream line")
        if "dropped upstream lines" not in out:
            fails.append("loss: --upstream mislabels its summary as 'fork'")

    with tempfile.TemporaryDirectory() as t:
        # a line that exists in the BASE is stale upstream, never "fork work"
        env = make_repo(t, "stale line present at the merge base already\n",
                        "stale line present at the merge base already\n",
                        "replacement line written by upstream instead\n",
                        "replacement line written by upstream instead\n")
        rc, out = run(LOSS, cwd=t, env=env)
        if "stale line" in out:
            fails.append("loss: flagged BASE content as fork work (false positive)")

    with tempfile.TemporaryDirectory() as t:
        # re-indented survivor must NOT be reported lost
        env = make_repo(t, "x = 1 and this line is long enough to count\n",
                        "x = 1 and this line is long enough to count\nfork helper line that is long enough\n",
                        "x = 1 and this line is long enough to count\n",
                        "x = 1 and this line is long enough to count\n    fork helper line that is long enough\n")
        rc, out = run(LOSS, cwd=t, env=env)
        if "fork helper line" in out:
            fails.append("loss: reported a RE-INDENTED surviving line as lost")

    # ---------------- classify_hunks: advisory, must never crash -------------
    with tempfile.TemporaryDirectory() as t:
        env = make_repo(t, "base only line long enough to be counted\n",
                        "base only line long enough to be counted\n",
                        "base only line long enough to be counted\n",
                        CONFLICT, path="c.py")
        rc, out = run(CLASSIFY, "c.py", cwd=t, env=env)
        if rc != 0:
            fails.append(f"classify: non-zero exit {rc}")
        if "suggested spec" not in out:
            fails.append("classify: no suggested spec emitted")

        rc, out = run(CLASSIFY, "does-not-exist.py", cwd=t, env=env)
        if rc != 0:
            fails.append("classify: crashed on a missing file")

    # ---------------- classify: add/add must be called UNION, not a side --------
    with tempfile.TemporaryDirectory() as t:
        # Both sides add DIFFERENT non-base content at the same spot. Choosing
        # either side silently drops the other's feature, so the tool must refuse
        # to suggest o/t here. This is the style.css failure mode: a fork theme
        # rule and an unrelated upstream widget landing at one offset.
        addadd = """base line that is long enough to count here
<<<<<<< HEAD
fork only rule that is long enough to count
=======
upstream only rule that is long enough here
>>>>>>> upstream-mirror
"""
        env = make_repo(t, "base line that is long enough to count here\n",
                        "base line that is long enough to count here\nfork only rule that is long enough to count\n",
                        "base line that is long enough to count here\nupstream only rule that is long enough here\n",
                        addadd, path="c.py")
        rc, out = run(CLASSIFY, "c.py", cwd=t, env=env)
        if "UNION" not in out:
            fails.append("classify: add/add hunk NOT flagged UNION (an o/t pick would drop a feature)")

    with tempfile.TemporaryDirectory() as t:
        # Only ONE side has non-base content -> that side moved last, and the tool
        # must still commit to it rather than punting everything to REVIEW.
        onesided = """base line that is long enough to count here
<<<<<<< HEAD
base line that is long enough to count here
=======
upstream only rule that is long enough here
>>>>>>> upstream-mirror
"""
        env = make_repo(t, "base line that is long enough to count here\n",
                        "base line that is long enough to count here\n",
                        "base line that is long enough to count here\nupstream only rule that is long enough here\n",
                        onesided, path="c.py")
        rc, out = run(CLASSIFY, "c.py", cwd=t, env=env)
        if "UNION" in out:
            fails.append("classify: one-sided change wrongly flagged UNION (false positive)")

    # ---------------- fork_work_loss --all: no silent truncation ----------------
    with tempfile.TemporaryDirectory() as t:
        # 9 dropped lines: the default view caps at 6, --all must show every one.
        # Without --all the obvious move is to hand-roll the same query, which is
        # how a tested tool gets bypassed mid-merge.
        forkside = "base line that is long enough to count here\n" + "".join(
            f"fork authored line number {i} long enough to count\n" for i in range(9))
        env = make_repo(t, "base line that is long enough to count here\n",
                        forkside,
                        "base line that is long enough to count here\n",
                        "base line that is long enough to count here\n", path="f.py")
        rc, out = run(LOSS, "f.py", cwd=t, env=env)
        if "and 3 more" not in out:
            fails.append("loss: default view no longer caps at 6 with a 'more' note")
        rc, out = run(LOSS, "--all", "f.py", cwd=t, env=env)
        if "more" in out.split("=====")[0]:
            fails.append("loss: --all still truncated the list")
        if sum(f"number {i} " in out for i in range(9)) != 9:
            fails.append("loss: --all did not print every dropped line")

    # ---------------- js_orphan_refs: must catch a real orphan, and stay quiet --
    with tempfile.TemporaryDirectory() as t:
        dev = ("const keep = 1;\nlet gone = 2;\nfunction f(){ return keep + gone; }\n")
        up  = ("const keep = 1;\nfunction f(){ return keep; }\n")
        # merge result: upstream's declaration set, but a surviving USE of `gone`
        bad = ("const keep = 1;\nfunction f(){ return keep + gone; }\n")
        env = make_repo(t, dev, dev, up, bad, path="m.js")
        rc, out = run(JSORPHAN, "m.js", cwd=t, env=env)
        if rc != 0:
            fails.append(f"js_orphan: non-zero exit {rc}")
        if "gone" not in out:
            fails.append("js_orphan: MISSED an orphaned reference (false negative)")

    with tempfile.TemporaryDirectory() as t:
        # the SAME name only inside a comment must NOT be reported -- comment noise
        # produced 11 false positives and 0 findings on the first real sweep.
        dev = "const keep = 1;\nlet gone = 2;\nfunction f(){ return keep + gone; }\n"
        up  = "const keep = 1;\nfunction f(){ return keep; }\n"
        ok  = "const keep = 1;\n// we no longer use gone here\nfunction f(){ return keep; }\n"
        env = make_repo(t, dev, dev, up, ok, path="m.js")
        rc, out = run(JSORPHAN, "m.js", cwd=t, env=env)
        if "gone" in out:
            fails.append("js_orphan: flagged a name that appears ONLY in a comment")

    # ---------------- rebase_staged: the SAFETY properties -------------------
    with tempfile.TemporaryDirectory() as t:
        # A repo shaped like a post-ingest fork: `old_mirror` is where the staged
        # branch was cut, then upstream-mirror moved on (RESET, not ff).
        env = make_repo(t, "base line that is long enough to be counted\n",
                        "base line that is long enough to be counted\n",
                        "base line that is long enough to be counted\nupstream added a line here ok\n",
                        "base line that is long enough to be counted\n")
        subprocess.run(["git", "tag", "oldmirror", "develop"], cwd=t, capture_output=True, env=env)
        subprocess.run(["git", "checkout", "-q", "-b", "fix/staged", "develop"], cwd=t, capture_output=True, env=env)
        pathlib.Path(t, "g.py").write_text("fork fix line long enough to count here\n")
        subprocess.run(["git", "add", "-A"], cwd=t, capture_output=True, env=env)
        subprocess.run(["git", "commit", "-qm", "fork fix"], cwd=t, capture_output=True, env=env)
        subprocess.run(["git", "checkout", "-q", "develop"], cwd=t, capture_output=True, env=env)
        before = subprocess.run(["git", "rev-parse", "fix/staged"], cwd=t,
                                capture_output=True, text=True, env=env).stdout.strip()

        # DRY RUN must move nothing. A tool that rewrites refs when you asked it
        # to report is unusable on 96 branches.
        rc, out = run(REBASE, "--old-mirror", "oldmirror", cwd=t, env=env)
        after = subprocess.run(["git", "rev-parse", "fix/staged"], cwd=t,
                               capture_output=True, text=True, env=env).stdout.strip()
        if after != before:
            fails.append("rebase_staged: DRY RUN moved a branch ref")
        if "DRY RUN" not in out:
            fails.append("rebase_staged: dry run not labelled as such")

        # APPLY must move the ref AND leave a rollback.
        rc, out = run(REBASE, "--old-mirror", "oldmirror", "--apply", cwd=t, env=env)
        after = subprocess.run(["git", "rev-parse", "fix/staged"], cwd=t,
                               capture_output=True, text=True, env=env).stdout.strip()
        roll = subprocess.run(["git", "rev-parse", "refs/prerebase/fix/staged"], cwd=t,
                              capture_output=True, text=True, env=env).stdout.strip()
        if after == before:
            fails.append("rebase_staged: --apply did not move the branch")
        if roll != before:
            fails.append("rebase_staged: rollback ref missing or wrong")

        # IDEMPOTENCE: re-running must SKIP, not reclassify. Once rebased, the
        # branch sits on the new mirror and every size heuristic misreads it --
        # this regressed once and flagged all 73 rebased branches as fork-only.
        rc, out = run(REBASE, "--old-mirror", "oldmirror", cwd=t, env=env)
        if "already on the current mirror" not in out:
            fails.append("rebase_staged: NOT idempotent — re-run did not skip a rebased branch")
        if "CLEAN (0)" not in out:
            fails.append("rebase_staged: re-run tried to rebase an already-rebased branch")

    # ---------------- scrub_attribution: content must NEVER change -----------
    with tempfile.TemporaryDirectory() as t:
        env = dict(os.environ, GIT_AUTHOR_NAME="A", GIT_AUTHOR_EMAIL="a@a",
                   GIT_COMMITTER_NAME="C", GIT_COMMITTER_EMAIL="c@c")
        subprocess.run(["git", "init", "-q", "-b", "develop", t], capture_output=True)
        f = pathlib.Path(t, "x.py"); f.write_text("one\n")
        subprocess.run(["git", "add", "-A"], cwd=t, capture_output=True, env=env)
        subprocess.run(["git", "commit", "-qm", "base"], cwd=t, capture_output=True, env=env)
        subprocess.run(["git", "tag", "mirror"], cwd=t, capture_output=True, env=env)
        subprocess.run(["git", "checkout", "-q", "-b", "fix/x"], cwd=t, capture_output=True, env=env)
        f.write_text("one\ntwo\n")
        subprocess.run(["git", "add", "-A"], cwd=t, capture_output=True, env=env)
        subprocess.run(["git", "commit", "-qm",
                        "fix: real subject\n\nBody line stays.\n\n"
                        "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"],
                       cwd=t, capture_output=True, env=env)
        before_tree = subprocess.run(["git", "rev-parse", "fix/x^{tree}"], cwd=t,
                                     capture_output=True, text=True, env=env).stdout.strip()
        before_tip = subprocess.run(["git", "rev-parse", "fix/x"], cwd=t,
                                    capture_output=True, text=True, env=env).stdout.strip()
        before_date = subprocess.run(["git", "log", "-1", "--format=%aI", "fix/x"], cwd=t,
                                     capture_output=True, text=True, env=env).stdout.strip()

        rc, out = run(SCRUB, "--base", "mirror", cwd=t, env=env)
        after = subprocess.run(["git", "rev-parse", "fix/x"], cwd=t,
                               capture_output=True, text=True, env=env).stdout.strip()
        if after != before_tip:
            fails.append("scrub: DRY RUN moved a branch ref")

        rc, out = run(SCRUB, "--base", "mirror", "--apply", "--verify", cwd=t, env=env)
        msg = subprocess.run(["git", "log", "-1", "--format=%B", "fix/x"], cwd=t,
                             capture_output=True, text=True, env=env).stdout
        tree = subprocess.run(["git", "rev-parse", "fix/x^{tree}"], cwd=t,
                              capture_output=True, text=True, env=env).stdout.strip()
        date = subprocess.run(["git", "log", "-1", "--format=%aI", "fix/x"], cwd=t,
                              capture_output=True, text=True, env=env).stdout.strip()
        roll = subprocess.run(["git", "rev-parse", "refs/prescrub/fix/x"], cwd=t,
                              capture_output=True, text=True, env=env).stdout.strip()

        if tree != before_tree:
            fails.append("scrub: CONTENT CHANGED — tree differs after scrubbing a message")
        if "Co-Authored-By" in msg or "anthropic" in msg.lower():
            fails.append("scrub: left an AI attribution trailer behind")
        if "fix: real subject" not in msg or "Body line stays." not in msg:
            fails.append("scrub: destroyed the real commit message")
        if date != before_date:
            fails.append("scrub: author date not preserved")
        if roll != before_tip:
            fails.append("scrub: rollback ref missing or wrong")

        # An already-merged branch must be refused: rewriting it rewrites pushed
        # history. This is the guard that a plain ancestor check does NOT provide.
        subprocess.run(["git", "checkout", "-q", "develop"], cwd=t, capture_output=True, env=env)
        subprocess.run(["git", "merge", "-q", "--no-edit", "fix/x"], cwd=t, capture_output=True, env=env)
        rc, out = run(SCRUB, "--base", "mirror", "--apply", "fix/x", cwd=t, env=env)
        if "already merged" not in out:
            fails.append("scrub: did NOT refuse a branch already merged into develop")

    for script in (RESOLVE, CLASSIFY, LOSS, JSORPHAN, REBASE, SURVEY, SCRUB):
        rc, out = run(script)                                   # no args
        if rc not in (0, 1, 2):
            fails.append(f"{script.name}: unexpected exit {rc} with no args")

    print(f"ran resolve/loss/classify batteries against {HERE}")
    if fails:
        print("\nFAILURES:")
        for f in fails:
            print("  -", f)
        return 1
    print("all passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
