"""The vendored evict arm must not rot away from the source it snapshots.

`tests/bench/vendor/messageWindow_fork.js` is a byte-snapshot of
`static/js/chatHistory.js` with a provenance header prepended. The benchmark
loads the snapshot (so it runs from any branch, deterministically) rather than
the live file. That buys reproducibility at the cost of a silent-staleness
risk: someone edits chatHistory.js, the bench keeps measuring the old code, and
the published artifact quietly describes a program that no longer exists.

This test closes that gap. It is skipped wherever the live file is absent --
which is every branch except the fork's `develop` -- so it never fails an
upstream checkout that legitimately has no chatHistory.js.
"""

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
LIVE = ROOT / "static/js/chatHistory.js"
SNAPSHOT = ROOT / "tests/bench/vendor/messageWindow_fork.js"

_MARKER = "// tests/test_bench_vendor_snapshot_drift.py asserts"


def _snapshot_body() -> str:
    """The snapshot minus its provenance header (everything up to the marker line)."""
    text = SNAPSHOT.read_text()
    idx = text.index(_MARKER)
    # skip the marker line and the two header lines that follow it, then the blank
    rest = text[idx:].split("\n", 3)[3]
    return rest


def test_snapshot_exists_and_is_labelled():
    assert SNAPSHOT.is_file(), "the evict arm's vendored snapshot is missing"
    head = SNAPSHOT.read_text(errors="replace")[:2000]
    # The header's central warning must survive edits: the snapshot is not the
    # code staged upstream, and a reader must not be able to miss that.
    assert "not* the eviction implementation" in head
    assert "sessions.js" in head
    assert "_evictHistoryOverflow" in head


@pytest.mark.skipif(not LIVE.is_file(), reason="no live chatHistory.js on this branch")
def test_snapshot_matches_live_chat_history():
    live = LIVE.read_text()
    snap = _snapshot_body()
    assert snap == live, (
        "tests/bench/vendor/messageWindow_fork.js has drifted from "
        "static/js/chatHistory.js. The benchmark measures the snapshot, so the "
        "published results in tests/bench/results/ now describe code that no "
        "longer exists. Re-vendor the snapshot and re-run the benchmark; do not "
        "just update this test."
    )
