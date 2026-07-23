"""qt_about.py — the shared, theme-aware About dialog for all three desktop
wrappers.

Two layers, mirroring how the repo tests the other Qt display code:

* Source-assertion checks run everywhere (including under the server venv's
  stub PyQt6, which has no real QtCore) and pin the theming invariants the
  FreeBSD pure-white report was about — OS colour-scheme detection, a palette
  fallback for platforms that report no scheme, and soft (never pure-white)
  surfaces.
* A behavioural check drives a *real* PyQt6 interpreter in a subprocess
  (the venv's PyQt6 is a stub, and the app conftest can't import under the
  system python, so neither can host the GUI directly). It self-skips when no
  real-PyQt6 interpreter is found.
"""
import os
import re
import subprocess
import sys
import textwrap

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = open(os.path.join(REPO, "qt_about.py"), encoding="utf-8").read()


# --- source-assertion layer (stub-safe) ------------------------------------

def test_uses_os_colour_scheme_then_palette_fallback():
    # Prefer the OS-reported scheme (Qt 6.5+)...
    assert "styleHints().colorScheme()" in SRC
    assert "Qt.ColorScheme.Dark" in SRC and "Qt.ColorScheme.Light" in SRC
    # ...then fall back to the window palette lightness when the platform
    # reports none (FreeBSD/OpenBSD with no platform-theme plugin).
    assert "QPalette.ColorRole.Window" in SRC and ".lightness()" in SRC


def test_surfaces_are_soft_never_pure_white_or_black():
    # The FreeBSD complaint was a harsh pure-white box; guard both surfaces
    # against #fff/#ffffff and #000/#000000.
    bgs = re.findall(r'"bg":\s*"(#[0-9a-fA-F]{3,6})"', SRC)
    assert len(bgs) >= 2, bgs
    banned = {"#fff", "#ffffff", "#000", "#000000"}
    assert not (set(b.lower() for b in bgs) & banned), bgs


def test_links_are_themed_explicitly():
    # Links carry an explicit colour so they stay legible on the dark surface
    # (Qt would otherwise paint them with the default light-mode link colour).
    assert SRC.count('<a style="color:{link}"') >= 3


def test_agpl_notice_preserved():
    assert "ABSOLUTELY NO WARRANTY" in SRC and "AGPL" in SRC


# --- behavioural layer (real PyQt6, via subprocess) ------------------------

def _real_pyqt_python():
    """Return a python interpreter with real PyQt6 (not the venv stub), or None."""
    for cand in ("/usr/bin/python3", sys.executable):
        try:
            r = subprocess.run(
                [cand, "-c", "import PyQt6.QtCore, PyQt6.QtWidgets"],
                capture_output=True, timeout=30)
            if r.returncode == 0:
                return cand
        except Exception:
            continue
    return None


_BEHAVIOUR = textwrap.dedent(r"""
    import os, sys
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, sys.argv[1])
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt
    import qt_about

    app = QApplication([])

    # Reported scheme wins outright, regardless of palette lightness.
    class _H:
        def __init__(s, v): s.v = v
        def colorScheme(s): return s.v
    class _C:
        def __init__(s, l): s.l = l
        def lightness(s): return s.l
    class _P:
        def __init__(s, l): s.c = _C(l)
        def color(s, _r): return s.c
    class _App:
        def __init__(s, sch, lit): s.h = _H(sch); s.p = _P(lit)
        def styleHints(s): return s.h
        def palette(s): return s.p

    assert qt_about._is_dark(_App(Qt.ColorScheme.Dark, 255)) is True
    assert qt_about._is_dark(_App(Qt.ColorScheme.Light, 0)) is False
    # FreeBSD/OpenBSD path: Unknown scheme -> palette lightness decides.
    assert qt_about._is_dark(_App(Qt.ColorScheme.Unknown, 30)) is True
    assert qt_about._is_dark(_App(Qt.ColorScheme.Unknown, 240)) is False

    light = qt_about.build_about_dialog(None, sys.argv[1], dark=False)
    dark = qt_about.build_about_dialog(None, sys.argv[1], dark=True)
    assert "#f4f4f5" in light.styleSheet(), light.styleSheet()
    assert "#26282c" in dark.styleSheet(), dark.styleSheet()
    assert light.windowTitle() == "About Odysseus"
    print("BEHAVIOUR_OK")
""")


def test_behaviour_real_pyqt6():
    py = _real_pyqt_python()
    if not py:
        pytest.skip("no real-PyQt6 interpreter available")
    r = subprocess.run([py, "-c", _BEHAVIOUR, REPO],
                       capture_output=True, text=True, timeout=60)
    assert "BEHAVIOUR_OK" in r.stdout, f"stdout={r.stdout!r} stderr={r.stderr!r}"
