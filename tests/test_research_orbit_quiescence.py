"""Research orbit ring quiescence (#115).

--research-orbit-angle feeds a conic-gradient + mask on .research-pane::after, so
advancing it every frame is a full-pane REPAINT. The driver must therefore run
only while a research job is active, pause when hidden / reduced-motion, throttle
the repaint, and freeze (not spin) when idle. Static assertions on the source.
"""
from pathlib import Path

_JS = (Path(__file__).resolve().parents[1] / "static" / "js" / "research" / "panel.js").read_text(encoding="utf-8")


def test_orbit_runs_only_when_job_active():
    # Driven by job state, not unconditionally on every sync.
    assert "_orbitActive = running > 0" in _JS
    # The old always-on call is gone.
    assert "_ensureOrbit()" not in _JS


def test_orbit_gated_on_visibility_and_reduced_motion():
    assert "function _orbitShouldRun" in _JS
    block = _JS[_JS.index("function _orbitShouldRun"): _JS.index("function _orbitShouldRun") + 320]
    assert "_orbitActive" in block
    assert "document.hidden" in block
    assert "prefers-reduced-motion" in block


def test_orbit_repaint_is_throttled():
    assert "_ORBIT_MIN_FRAME_MS" in _JS
    # Throttle compares elapsed time before writing the CSS property.
    assert "_orbitLastPaintTs" in _JS
    assert "setProperty('--research-orbit-angle'" in _JS


def test_orbit_reevaluates_on_visibility_change():
    assert "addEventListener('visibilitychange', _updateOrbit)" in _JS


def test_orbit_stops_loop_when_should_not_run():
    # cancelAnimationFrame path so a finished job / background freezes cleanly.
    assert "cancelAnimationFrame(_orbitRAF)" in _JS
