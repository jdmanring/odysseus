"""Research orbit ring: compositor-driven + quiescent (#115).

The orbit ring is a STATIC conic-gradient rotated by a CSS compositor transform
(no per-frame repaint). JS only toggles `.orbit-active` from job state; CSS spins
it while active and freezes/pauses it when idle, backgrounded, or reduced-motion.
Static assertions on source.
"""
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_JS = (_ROOT / "static" / "js" / "research" / "panel.js").read_text(encoding="utf-8")
_CSS = (_ROOT / "static" / "style.css").read_text(encoding="utf-8")


def test_js_only_toggles_active_class_no_raf():
    # Drive purely by a class toggle from job state…
    assert "classList.toggle('orbit-active', running > 0)" in _JS
    # …and the per-frame rAF repaint machinery is gone.
    assert "requestAnimationFrame" not in _JS
    assert "--research-orbit-angle" not in _JS
    assert "_orbitRAF" not in _JS


def test_js_injects_compositor_orbit_dom():
    assert "research-orbit-spin" in _JS
    assert "research-orbit" in _JS


def test_css_orbit_is_transform_animation():
    assert "@keyframes research-orbit-spin" in _CSS
    block = _CSS[_CSS.index("@keyframes research-orbit-spin"):][:120]
    assert "rotate(360deg)" in block  # compositor transform, not a gradient angle
    assert "--research-orbit-angle" not in _CSS  # old per-frame paint var removed


def test_css_spins_only_when_active_and_quiesces():
    assert ".research-orbit-spin" in _CSS
    # Paused by default, runs only on .orbit-active.
    assert "animation-play-state: paused" in _CSS
    assert ".research-pane.orbit-active .research-orbit-spin { animation-play-state: running" in _CSS
    # Quiescence: backgrounded + reduced-motion.
    assert "html.app-blurred .research-orbit-spin { animation-play-state: paused" in _CSS
    assert "prefers-reduced-motion" in _CSS
