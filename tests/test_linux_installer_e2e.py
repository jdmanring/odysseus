"""Behavioral E2E: build-linux-app.sh actually installs the XDG desktop app.

Runs the real installer against a sandboxed $HOME (so it never touches the
developer's ~/.local) and asserts the launcher, .desktop entry, and icon are
created and internally consistent. This converts the one-off manual bench proof
into a repeatable test.
"""
import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.skipif(
    os.uname().sysname not in ("Linux", "FreeBSD"),
    reason="XDG desktop installer (Linux/FreeBSD)",
)


def _system_qt_ok() -> bool:
    return subprocess.run(
        ["/usr/bin/python3", "-c", "import PyQt6.QtWebEngineWidgets"],
        capture_output=True,
    ).returncode == 0


def test_build_linux_app_installs_desktop_launcher_icon(tmp_path):
    if not (REPO / "venv" / "bin" / "python").exists():
        pytest.skip("repo venv not built")
    if not _system_qt_ok():
        pytest.skip("system PyQt6 WebEngine not available")

    env = dict(os.environ, HOME=str(tmp_path))
    r = subprocess.run(
        ["bash", str(REPO / "build-linux-app.sh")],
        env=env, capture_output=True, text=True, timeout=180,
    )
    assert r.returncode == 0, f"installer failed:\n{r.stdout}\n{r.stderr}"

    launcher = tmp_path / ".local/bin/odysseus"
    desktop = tmp_path / ".local/share/applications/odysseus.desktop"
    icon = tmp_path / ".local/share/icons/hicolor/scalable/apps/odysseus.svg"

    assert launcher.exists(), "launcher not installed"
    assert os.access(launcher, os.X_OK), "launcher not executable"
    assert desktop.exists(), ".desktop entry not installed"
    assert icon.exists(), "icon not installed"

    # The .desktop must launch the installed launcher and be a valid entry.
    dtext = desktop.read_text(encoding="utf-8")
    assert "[Desktop Entry]" in dtext
    assert f"Exec={launcher}" in dtext
    assert "Type=Application" in dtext

    # The launcher must drive the repo (system python3 for the wrapper, venv for
    # the backend — the two-interpreter model) — i.e. it references the repo.
    ltext = launcher.read_text(encoding="utf-8")
    assert str(REPO) in ltext


def test_installer_is_idempotent(tmp_path):
    """Re-running the installer over an existing install must succeed cleanly."""
    if not (REPO / "venv" / "bin" / "python").exists() or not _system_qt_ok():
        pytest.skip("prereqs unavailable")
    env = dict(os.environ, HOME=str(tmp_path))
    for _ in range(2):
        r = subprocess.run(
            ["bash", str(REPO / "build-linux-app.sh")],
            env=env, capture_output=True, text=True, timeout=180,
        )
        assert r.returncode == 0, r.stderr
    assert (tmp_path / ".local/share/applications/odysseus.desktop").exists()
