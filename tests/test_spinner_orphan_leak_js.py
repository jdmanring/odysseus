"""Source-text guards for the whirlpool spinner orphan/hidden leak fix
(jdmanring#107).

The whirlpool spinner runs a requestAnimationFrame loop. Its self-terminate
guard previously kept looping forever while `!_wpWasConnected`, so a spinner that
was started but never appended (or one inside a display:none panel) burned CPU
and churned canvas allocations indefinitely. The loop must stop when the spinner
is not doing visible work.
"""
from pathlib import Path

_SRC = (Path(__file__).resolve().parents[1] / "static/js/spinner.js").read_text(encoding="utf-8")


def _whirlpool_tail() -> str:
    # The self-terminate region: from the frame increment to the end of the method.
    start = _SRC.index("this._wpFrame++;")
    end = _SRC.index("\n  }", start)
    return _SRC[start:end]


def test_grace_frames_constant_defined():
    assert "_WP_ORPHAN_GRACE_FRAMES" in _SRC


def test_terminate_gates_on_visibility_not_just_connected():
    # isConnected is true for display:none; the guard must require offsetParent.
    tail = _whirlpool_tail()
    assert "offsetParent" in tail
    assert "isConnected" in tail


def test_orphan_grace_window_is_bounded():
    # An unappended spinner must give up after the bounded grace window rather
    # than looping forever on the old unbounded `!_wpWasConnected` branch.
    tail = _whirlpool_tail()
    assert "_WP_ORPHAN_GRACE_FRAMES" in tail
    assert "withinGrace" in tail


def test_unbounded_never_connected_branch_removed():
    # The old guard that looped forever when never connected must be gone.
    assert "connected || !this._wpWasConnected" not in _SRC
    assert "_wpWasConnected" not in _SRC


def test_loop_still_runs_while_visible():
    tail = _whirlpool_tail()
    assert "requestAnimationFrame(() => this._drawWhirlpool())" in tail
    assert "this.isRunning = false;" in tail
