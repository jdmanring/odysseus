"""The vendored #4661 arm must stay faithful to its source commit.

tests/bench/vendor/trimChatHistory_4661.js is an extraction of upstream PR
#4661's _trimChatHistoryDOM + _loadOlderMessages (commit 27f35e1c) with marked
harness adapters (renderer/fetch/session). If the PR's constants or removal/
teardown logic drift in the vendor, the benchmark measures a strawman -- these
checks pin the load-bearing lines to the PR's own.
"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = (ROOT / "tests/bench/vendor/trimChatHistory_4661.js").read_text(encoding="utf-8")


def test_provenance_header():
    assert "27f35e1c1303ec9732bae68e8c32c14ebd3e82a6" in SRC
    assert "VENDORED SNAPSHOT" in SRC
    assert "HARNESS ADAPTER" in SRC  # adapters are marked, not silent


def test_prs_own_constants():
    assert "var MAX_CHAT_DOM_NODES = 150;" in SRC
    assert "Math.min(20, Math.floor(MAX_CHAT_DOM_NODES / 4))" in SRC  # keepFloor
    assert "fetch(" not in SRC  # network adapted away (corpus slice)...
    assert "_unloadedMsgCount - 50" in SRC  # ...but the PR's offset arithmetic kept


def test_prs_own_teardown_lines():
    # The teardown block is the PR's, verbatim: intervals, spinner, thread
    # nodes, data-URI blanking.
    for line in (
        "if (el._waveInterval) { clearInterval(el._waveInterval); el._waveInterval = null; }",
        "if (el._elapsedTicker) { clearInterval(el._elapsedTicker); el._elapsedTicker = null; }",
        "if (el._spinner) { try { el._spinner.destroy(); } catch (_) {} }",
        ".agent-thread-node",
        "img[src^=\"data:\"]",
    ):
        assert line in SRC, line


def test_prs_own_removal_loop_shape():
    # Oldest-first removal with the PR's index re-check after live-collection shift.
    assert "children.length > MAX_CHAT_DOM_NODES; i++" in SRC
    assert "i--;" in SRC


def test_no_fork_logic_leaked_in():
    # The arm must measure #4661, not the fork: none of MessageWindow's
    # machinery may appear.
    for token in ("_pruneTop", "_estFold", "_updateTopSpacer", "BIDI_", "chIdx"):
        assert token not in SRC, token
