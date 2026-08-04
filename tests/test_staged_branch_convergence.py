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
NAMEERROR_BRANCH = "fix/chat-stream-web-intent-nameerror"
ARIA2C_BRANCH = "feat/aria2c-downloader"
TRUNCATE_BRANCH = "fix/truncate-fork-by-msg-id"

# (staged branch, repo-relative path, whole-line comment prefix)
CONVERGED_FILES = [
    (STAGED_BRANCH, "static/js/chatHistory.js", "//"),
    (STAGED_BRANCH, "static/app.js", "//"),
    (STAGED_BRANCH, "static/js/keyboard-shortcuts.js", "//"),
    (STAGED_BRANCH, "tests/test_chat_history_js.py", "#"),
    (STAGED_BRANCH, "tests/test_chat_history_playwright.py", "#"),
    (STAGED_BRANCH, "tests/test_chat_history_a11y_js.py", "#"),
    (STAGED_BRANCH, "tests/test_chat_history_render_paging_playwright.py", "#"),
    (STAGED_BRANCH, "tests/bench/live_app.py", "#"),
    (STAGED_BRANCH, "tests/bench/scroll_driver.js", "//"),
    (STAGED_BRANCH, "tests/bench/mock_llm.py", "#"),
    (STAGED_BRANCH, "tests/test_chat_history_longsession_playwright.py", "#"),
    (NAMEERROR_BRANCH, "tests/test_routes_defined_names.py", "#"),
    # This module does not exist upstream, so its temp-db cleanup is written
    # self-contained rather than through tests/helpers/temp_cleanup.py: the
    # staged branch must stay independently fileable and cannot depend on the
    # unfiled helper (#174). That leaves two cleanup mechanisms on develop, so
    # guard the pair against drifting apart.
    (TRUNCATE_BRANCH, "tests/test_truncate_fork_by_msg_id.py", "#"),
    # aria2c branch (issue #146 rebuild): wholesale copies of develop's files.
    # routes/cookbook_routes.py is deliberately NOT listed — the branch version
    # legitimately differs in code (no basicsr calls; carries the stacked
    # /resolve-gguf endpoint), so only the shared-verbatim files are guarded.
    (ARIA2C_BRANCH, "static/js/cookbookRunning.js", "//"),
    (ARIA2C_BRANCH, "static/js/cookbookDownload.js", "//"),
    (ARIA2C_BRANCH, "tooling/aria2c_download.py", "#"),
    (ARIA2C_BRANCH, "tooling/bin_manager.py", "#"),
    (ARIA2C_BRANCH, "tests/test_aria2c_circuit.py", "#"),
    (ARIA2C_BRANCH, "tests/test_aria2c_launcher_wiring.py", "#"),
    (ARIA2C_BRANCH, "tests/tooling/test_bin_manager.py", "#"),
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


def _branch_available(branch: str, probe_path: str) -> bool:
    return _git_show(branch, probe_path) is not None


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

@pytest.mark.parametrize("branch,path,prefix", CONVERGED_FILES,
                         ids=[p for _, p, _pfx in CONVERGED_FILES])
def test_staged_branch_matches_maintained(branch, path, prefix):
    if not _branch_available(branch, path):
        pytest.skip(f"no {branch} branch in this checkout")
    live = (ROOT / path).read_text(encoding="utf-8")
    staged = _git_show(branch, path)
    assert staged is not None, f"{path} missing on {branch}"
    assert _normalize(staged, prefix) == _normalize(live, prefix), (
        f"{path} on {branch} has drifted from the maintained version "
        f"(comments excluded). The staged upstream artifact is stale: re-converge "
        f"it (checkout the branch, `git checkout develop -- <files>`, re-apply the "
        f"comment-only fork-reference scrub, run the branch's suites, commit) "
        f"before any further chat-history work lands. See issue #131."
    )
