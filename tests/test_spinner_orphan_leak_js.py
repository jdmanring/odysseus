"""Source-text guards for the spinner orphan/hidden leak fix (jdmanring#107).

All three animated spinners run a continuous loop: whirlpool and sinewave via
requestAnimationFrame, the ASCII spinner via setInterval. Each previously kept
looping regardless of whether its element was visible, so a spinner that was
started but never appended (or one inside a display:none panel) burned CPU and
churned allocations forever. A single shared guard, _shouldKeepSpinning(), stops
all three when the spinner is not doing visible work.
"""
from pathlib import Path

_SRC = (Path(__file__).resolve().parents[1] / "static/js/spinner.js").read_text(encoding="utf-8")


def _guard_body() -> str:
    start = _SRC.index("_shouldKeepSpinning() {")
    end = _SRC.index("\n  }", start)
    return _SRC[start:end]


def test_shared_guard_and_grace_constant_exist():
    assert "_shouldKeepSpinning() {" in _SRC
    assert "_SPIN_ORPHAN_GRACE_MS" in _SRC


def test_guard_gates_on_visibility_not_just_connected():
    # isConnected is true for display:none; the guard must require offsetParent.
    body = _guard_body()
    assert "offsetParent" in body
    assert "isConnected" in body


def test_guard_bounds_the_never_visible_grace():
    # An unappended spinner must give up after the bounded grace window rather
    # than looping forever.
    body = _guard_body()
    assert "_SPIN_ORPHAN_GRACE_MS" in body
    assert "_spinWasVisible" in body  # was-visible-then-hidden -> stop


def test_all_three_loops_consult_the_guard():
    # whirlpool (rAF), sinewave (rAF), and ASCII (setInterval) must all gate their
    # continuation on the shared guard.
    assert _SRC.count("_shouldKeepSpinning()") >= 4  # def + 3 call sites
    # The ASCII setInterval path must stop() when the guard fails.
    idx = _SRC.index("this.intervalId = setInterval(")
    block = _SRC[idx: idx + 300]
    assert "_shouldKeepSpinning()" in block
    assert "this.stop()" in block


def test_old_unbounded_guards_removed():
    # The earlier per-loop guards that could loop forever must be gone.
    assert "_wpWasConnected" not in _SRC
    assert "_WP_ORPHAN_GRACE_FRAMES" not in _SRC
