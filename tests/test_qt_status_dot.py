"""qt_status_dot.py — coloured tray status-dot icons shared by qt_wrapper.py and
windows_wrapper.py.

Source-assertion layer runs under the venv stub PyQt6; the behavioural layer
drives a real PyQt6 interpreter in a subprocess (the venv PyQt6 is a stub and
the app conftest can't import under the system python) and self-skips if none
is found. The behavioural check asserts the *Disabled-mode* pixmap keeps its
colour — a plain setIcon on the disabled status action would grey out, which is
exactly the bug this module exists to avoid.
"""
import os
import subprocess
import sys
import textwrap

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = open(os.path.join(REPO, "qt_status_dot.py"), encoding="utf-8").read()


# --- source-assertion layer (stub-safe) ------------------------------------

def test_three_states_defined():
    assert '"running"' in SRC and '"stopped"' in SRC and '"busy"' in SRC


def test_running_green_stopped_red():
    # Green for running, red for stopped — the whole point.
    assert "#3fb950" in SRC  # green
    assert "#f85149" in SRC  # red


def test_disabled_mode_pixmap_pinned():
    # The colour must be pinned for the Disabled mode or Qt greys it out on the
    # disabled status action.
    assert "QIcon.Mode.Disabled" in SRC


# --- behavioural layer (real PyQt6, via subprocess) ------------------------

def _real_pyqt_python():
    for cand in ("/usr/bin/python3", sys.executable):
        try:
            r = subprocess.run([cand, "-c", "import PyQt6.QtGui, PyQt6.QtWidgets"],
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
    from PyQt6.QtGui import QIcon
    from PyQt6.QtCore import QSize
    import qt_status_dot
    app = QApplication([])
    want = {"running": (63, 185, 80), "stopped": (248, 81, 73), "busy": (210, 153, 34)}
    for state, (r, g, b) in want.items():
        icon = qt_status_dot.status_dot(state, px=16)
        # Disabled mode is what the disabled status action renders — must stay coloured.
        pm = icon.pixmap(QSize(16, 16), QIcon.Mode.Disabled)
        assert not pm.isNull(), state
        c = pm.toImage().pixelColor(8, 8)
        assert abs(c.red()-r) < 45 and abs(c.green()-g) < 45 and abs(c.blue()-b) < 45, \
            (state, c.red(), c.green(), c.blue())
    # running must be visibly greener-than-red; stopped redder-than-green.
    run = qt_status_dot.status_dot("running", 16).pixmap(QSize(16,16)).toImage().pixelColor(8,8)
    stop = qt_status_dot.status_dot("stopped", 16).pixmap(QSize(16,16)).toImage().pixelColor(8,8)
    assert run.green() > run.red() and stop.red() > stop.green()
    print("DOT_OK")
""")


def test_behaviour_real_pyqt6():
    import pytest
    py = _real_pyqt_python()
    if not py:
        pytest.skip("no real-PyQt6 interpreter available")
    r = subprocess.run([py, "-c", _BEHAVIOUR, REPO],
                       capture_output=True, text=True, timeout=60)
    assert "DOT_OK" in r.stdout, f"stdout={r.stdout!r} stderr={r.stderr!r}"
