"""Fork-workbench guard: the staged upstream branch must not lag the maintained code.

Three times in one cycle a fix landed on develop while the staged upstream branch
(`fix/dom-oom-virtualization`) silently kept a stale chatHistory.js -- the
staged-artifact-lag defect class. The branch was converged to the maintained
version (byte-identical except fork-issue references scrubbed from comments);
this guard makes the next lag mechanically impossible to miss, exactly as
tests/test_bench_vendor_snapshot_drift.py does for the vendored bench snapshot.

Comparison is normalized: whole-line comments and blank lines are stripped from
both sides, because the staged branch legitimately differs only in scrubbed
fork-issue references, which live in comments. Any CODE drift fails.

Known limitation (by design): drift confined to comments or docstrings is
invisible to the guard. Keep scrub edits comment-only; if a scrub ever needs to
touch code, this guard fails and forces a conscious re-convergence.

Skips cleanly when git or the staged branch is absent, so it is inert on any
checkout that is not this fork's develop (including an upstream checkout if it
ever leaked into a PR -- it must not; this file is fork-only, issue #131).
"""
import pathlib
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
STAGED_BRANCH = "fix/dom-oom-virtualization"

# (repo-relative path, whole-line comment prefix)
CONVERGED_FILES = [
    ("static/js/chatHistory.js", "//"),
    ("tests/test_chat_history_js.py", "#"),
    ("tests/test_chat_history_playwright.py", "#"),
    ("tests/test_chat_history_a11y_js.py", "#"),
    ("tests/test_chat_history_render_paging_playwright.py", "#"),
    ("tests/bench/live_app.py", "#"),
    ("tests/bench/scroll_driver.js", "//"),
]


def _git_show(ref: str, path: str):
    try:
        r = subprocess.run(
            ["git", "-C", str(ROOT), "show", f"{ref}:{path}"],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 else None


def _normalize(text: str, comment_prefix: str) -> str:
    """Strip whole-line comments and blank lines; everything else must match."""
    kept = []
    for line in text.split("\n"):
        s = line.strip()
        if not s or s.startswith(comment_prefix):
            continue
        # For JS files, whole-line block-comment lines (/* ... */ bodies) are
        # comments too -- fork-issue refs live there and may be scrubbed on the
        # staged branch just like // lines.
        if comment_prefix == "//" and (s.startswith("*") or s.startswith("/*")):
            continue
        kept.append(line)
    return "\n".join(kept)


def _branch_available() -> bool:
    return _git_show(STAGED_BRANCH, CONVERGED_FILES[0][0]) is not None


# ---------------------------------------------------------------------------
# Normalizer contract (mutation checks -- the guard is only as good as these)
# ---------------------------------------------------------------------------

def test_normalizer_ignores_comment_only_drift():
    a = "var x = 1;\n// fixed per issue #999\nload(x);"
    b = "var x = 1;\n// fixed\nload(x);"
    assert _normalize(a, "//") == _normalize(b, "//")


def test_normalizer_ignores_blank_line_drift():
    assert _normalize("a = 1\n\n\nb = 2", "#") == _normalize("a = 1\nb = 2", "#")


def test_normalizer_detects_code_drift():
    a = "var x = 1;\nload(x);"
    b = "var x = 2;\nload(x);"
    assert _normalize(a, "//") != _normalize(b, "//")


def test_normalizer_detects_trailing_comment_code_drift():
    # A trailing comment shares its line with code; the line is kept whole, so
    # code changes on such lines are still detected.
    a = "x = 1  # tuned"
    b = "x = 2  # tuned"
    assert _normalize(a, "#") != _normalize(b, "#")


# ---------------------------------------------------------------------------
# The guard
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _branch_available(),
                    reason=f"no {STAGED_BRANCH} branch in this checkout")
@pytest.mark.parametrize("path,prefix", CONVERGED_FILES,
                         ids=[p for p, _ in CONVERGED_FILES])
def test_staged_branch_matches_maintained(path, prefix):
    live = (ROOT / path).read_text(encoding="utf-8")
    staged = _git_show(STAGED_BRANCH, path)
    assert staged is not None, f"{path} missing on {STAGED_BRANCH}"
    assert _normalize(staged, prefix) == _normalize(live, prefix), (
        f"{path} on {STAGED_BRANCH} has drifted from the maintained version "
        f"(comments excluded). The staged upstream artifact is stale: re-converge "
        f"it (checkout the branch, `git checkout develop -- <files>`, re-apply the "
        f"comment-only fork-reference scrub, run the branch's suites, commit) "
        f"before any further chat-history work lands. See issue #131."
    )
