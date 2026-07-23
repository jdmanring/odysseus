"""setup.sh / setup.ps1 — one-command from-scratch provisioners.

They give Linux/*BSD (setup.sh) and Windows (setup.ps1) the one-command setup
macOS has via start-macos.sh: ensure the interpreter, build the venv + install
requirements, run first-run setup, then install the native app. Verified
end-to-end on Arch Linux (system Qt + pacman): detection → venv → setup.py →
.desktop/launcher/icon install.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SETUP_SH = (REPO / "setup.sh").read_text(encoding="utf-8")
SETUP_PS1 = (REPO / "setup.ps1").read_text(encoding="utf-8")
INSTALL_SH = (REPO / "install.sh").read_text(encoding="utf-8")


def test_setup_sh_is_posix_sh():
    # Must run on OpenBSD's /bin/sh (no bash in base).
    assert SETUP_SH.splitlines()[0] == "#!/bin/sh"


def test_setup_sh_handles_the_unix_platforms():
    assert "Linux | FreeBSD | OpenBSD)" in SETUP_SH
    # macOS is delegated to its own provisioner, not duplicated here.
    assert "start-macos.sh" in SETUP_SH


def test_setup_sh_does_not_pip_install_pyqt_on_linux_bsd():
    # The display layer runs under the SYSTEM python3; pip-ing PyQt into the venv
    # would download ~250 MB the system python3 can't even import. venv = server
    # deps only; Qt is the system package (guided).
    assert "pip install PyQt" not in SETUP_SH
    assert "pip install -r requirements.txt" in SETUP_SH


def test_setup_sh_guides_the_privileged_qt_step_per_pm():
    # No-sudo: print the exact package-manager command, don't run it.
    for hint in ("pacman -S python-pyqt6", "apt install python3-pyqt6",
                 "pkg install py311-qt6-webengine", "pkg_add py3-qt6webengine"):
        assert hint in SETUP_SH


def test_setup_sh_is_idempotent_and_installs_app():
    assert "venv/.requirements_hash" in SETUP_SH          # skip pip when unchanged
    assert "exec ./install.sh" in SETUP_SH                # provision -> install


def test_setup_ps1_checks_python_and_delegates_to_installer():
    assert "Python 3.11+" in SETUP_PS1
    assert "install.bat" in SETUP_PS1
    assert "setup.py" in SETUP_PS1


def test_installsh_openbsd_uses_sh():
    assert 'exec sh "$SCRIPT_DIR/build-openbsd-app.sh"' in INSTALL_SH
