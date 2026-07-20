"""Static guard: animated canvas background patterns honor prefers-reduced-motion.

theme.js must gate the canvas pattern runners at the applyBgPattern choke
point (login routes through it too), and re-apply the pattern when the OS
setting changes so a toggle takes effect live.
"""
from pathlib import Path

THEME = (
    Path(__file__).resolve().parent.parent / "static" / "js" / "theme.js"
).read_text(encoding="utf-8")


def test_defines_reduced_motion_media_query():
    assert "_REDUCED_MOTION" in THEME
    assert "prefers-reduced-motion: reduce" in THEME


def test_canvas_patterns_gated_on_reduced_motion():
    assert (
        "_CANVAS_PATTERNS[p] && !(_REDUCED_MOTION && _REDUCED_MOTION.matches)"
        in THEME
    )


def test_reapplies_pattern_when_os_setting_changes():
    assert "_REDUCED_MOTION.addEventListener('change'" in THEME
    assert "applyBgPattern(_lastPattern)" in THEME
