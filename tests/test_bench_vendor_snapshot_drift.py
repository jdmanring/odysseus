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

It also pins the two vendored UPSTREAM arms by content hash. Those cannot drift
from their source (both PRs are closed, so the source is frozen), but they can be
edited here -- and the first question a PR author asks about a benchmark of their
own code is "how do I know you did not tweak it?". A hash makes that verifiable
instead of trusted: the header cites the exact source commit, so anyone can fetch
it, diff, and confirm the hash below. Changing either file must be a deliberate
re-vendor that updates this constant and re-runs the benchmark.
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


# sha256 of the vendored upstream arms, as benchmarked for
# tests/bench/results/bench.md (generated 2026-07-25). These are OTHER PEOPLE'S
# code, measured to compare against ours, so their integrity is the load-bearing
# claim in any citation of those results.
VENDORED_UPSTREAM = {
    "trimChatHistory_4661.js": (
        "ae8af6113b3eec96ab5b6654c2b4a0120e1785d466f72f705ec98b55896bfa92",
        "27f35e1c1303ec9732bae68e8c32c14ebd3e82a6",   # upstream PR #4661
    ),
    "chatVirtualizer_4998.js": (
        "73d55d25725713f03d4781b76ba709702a36eac650ef5c3d658fefc1b15011d0",
        None,                                          # upstream PR #4998, vendored byte-for-byte
    ),
}


@pytest.mark.parametrize("name", sorted(VENDORED_UPSTREAM))
def test_vendored_upstream_arm_is_unmodified(name):
    """A benchmark of someone else's code is only evidence if their code is intact."""
    import hashlib

    path = ROOT / "tests/bench/vendor" / name
    assert path.is_file(), f"vendored upstream arm {name} is missing"
    expected, _commit = VENDORED_UPSTREAM[name]
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    assert actual == expected, (
        f"{name} has been modified since it was benchmarked.\n"
        f"  expected {expected}\n  actual   {actual}\n"
        "tests/bench/results/bench.md compares OUR implementation against this "
        "one; editing it invalidates that comparison and makes the published "
        "numbers uncitable. If this is a deliberate re-vendor, update the hash "
        "here AND re-run tests/bench/chat_history_bench.py."
    )


@pytest.mark.parametrize("name", sorted(VENDORED_UPSTREAM))
def test_vendored_upstream_arm_states_its_provenance(name):
    """The header is what lets a reviewer verify the hash against the real source."""
    head = (ROOT / "tests/bench/vendor" / name).read_text(errors="replace")[:1200]
    assert "VENDORED" in head.upper(), f"{name} must announce that it is vendored"
    assert "upstream PR #" in head, f"{name} must name the upstream PR it came from"
    _expected, commit = VENDORED_UPSTREAM[name]
    if commit:
        assert commit in head, (
            f"{name}'s header must cite the source commit {commit} so a reviewer "
            "can fetch it and diff against this file"
        )
