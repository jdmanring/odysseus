"""Shared, theme-aware About dialog for the Odysseus desktop wrappers.

Qt-only — no ``/proc``, ``/sys`` or ctypes — so all three wrappers import it
directly, the same way they already share ``qt_watchdog.py``:
``qt_wrapper.py`` (Linux/FreeBSD/OpenBSD), ``mac_wrapper.py`` and
``windows_wrapper.py``. Extracted 2026-07-23 from three byte-identical copies.

The dialog follows the OS light/dark setting where the platform reports it
(Qt 6.5+ ``QStyleHints.colorScheme``). Where no Qt platform-theme plugin is
present — notably FreeBSD/OpenBSD, where ``colorScheme()`` is ``Unknown`` and
the palette defaults to bare white — it falls back to the window-palette
lightness. In every case the surface is a soft tone, never a harsh pure-white
``#fff`` (the box users reported as painful on FreeBSD). The fill is flat and
painted once, so it carries no per-frame cost.
"""
import os
import re as _re

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QPalette
from PyQt6.QtWidgets import (QApplication, QDialog, QLabel, QVBoxLayout,
                             QHBoxLayout, QPushButton)

# Canonical project details for the About dialog (from the upstream README).
_ABOUT_GITHUB = "https://github.com/odysseus-dev/odysseus"
_ABOUT_LICENSE = "https://github.com/odysseus-dev/odysseus/blob/main/LICENSE"
_ABOUT_ISSUES = "https://github.com/odysseus-dev/odysseus/issues"

# Two small palettes. Neither surface is pure #fff / #000: a flat pure-white
# box is what reads as harsh, and a soft tone still contrasts its own text.
_LIGHT = {"bg": "#f4f4f5", "fg": "#1f2124", "muted": "#6b7280", "link": "#2563eb"}
_DARK = {"bg": "#26282c", "fg": "#e6e7ea", "muted": "#9aa0aa", "link": "#7aa2f7"}


def _app_version(install_dir):
    """Read APP_VERSION from src/constants.py by text scan. Importing the module
    would pull in runtime path deps the wrapper deliberately avoids; a regex over
    one line is enough and never fails the dialog. Returns '' if unavailable."""
    try:
        with open(os.path.join(install_dir, "src", "constants.py"), encoding="utf-8") as fh:
            for line in fh:
                m = _re.match(r"""\s*APP_VERSION\s*=\s*["']([^"']+)["']""", line)
                if m:
                    return m.group(1)
    except Exception:
        pass
    return ""


def _is_dark(app):
    """True when the dialog should paint dark. Prefer the OS-reported colour
    scheme (Qt 6.5+); fall back to the window-palette lightness when the
    platform exposes none (``colorScheme()`` is ``Unknown`` on FreeBSD/OpenBSD
    with no platform-theme plugin)."""
    try:
        scheme = app.styleHints().colorScheme()
        if scheme == Qt.ColorScheme.Dark:
            return True
        if scheme == Qt.ColorScheme.Light:
            return False
    except (AttributeError, TypeError):
        pass  # Qt < 6.5 has no colorScheme(); fall through to the palette.
    return app.palette().color(QPalette.ColorRole.Window).lightness() < 128


def _resolve_colors(dark):
    """dark: True/False forces a scheme; None auto-detects from the running app."""
    if dark is None:
        app = QApplication.instance()
        dark = bool(app is not None and _is_dark(app))
    return _DARK if dark else _LIGHT


def about_html(colors, version):
    subtitle = f"Version {version}" if version else "Desktop app"
    fg, muted, link = colors["fg"], colors["muted"], colors["link"]
    # AGPL-3.0 §5 requires an interactive UI to show a copyright notice and the
    # no-warranty statement; the About box is where those live. Colours are set
    # inline so the rich text stays legible on the explicit surface below.
    return (
        f'<div style="min-width:380px;color:{fg}">'
        f'<h2 style="margin:0 0 2px;color:{fg}">Odysseus</h2>'
        f'<p style="margin:0 0 12px;color:{muted}">{subtitle}</p>'
        f'<p style="margin:0 0 12px;color:{fg}">A self-hosted AI workspace for chat, agents, '
        'research, documents, email, notes, calendar, and local model workflows.</p>'
        f'<p style="margin:0 0 8px;color:{fg}">&#169; The Odysseus authors &#183; '
        f'<a style="color:{link}" href="{_ABOUT_LICENSE}">AGPL-3.0-or-later</a></p>'
        f'<p style="margin:0 0 12px;font-size:small;color:{muted}">This program comes '
        'with ABSOLUTELY NO WARRANTY. It is free software, and you are welcome to '
        'redistribute it under the terms of the GNU AGPL, version 3 or later.</p>'
        f'<p style="margin:0;color:{fg}">'
        f'<a style="color:{link}" href="{_ABOUT_GITHUB}">Website</a> &#183; '
        f'<a style="color:{link}" href="{_ABOUT_ISSUES}">Report an issue</a></p>'
        '</div>')


def build_about_dialog(parent, install_dir, dark=None):
    """Build the About dialog without showing it. ``dark`` forces a scheme
    (True/False) or auto-detects (None); the explicit ``dark`` hook keeps the
    dialog renderable offscreen for both themes in tests."""
    colors = _resolve_colors(dark)

    dlg = QDialog(parent)
    dlg.setWindowTitle("About Odysseus")
    # Explicit surface so the box never inherits a bare pure-white palette
    # (the FreeBSD/OpenBSD default) and always contrasts its own text.
    dlg.setStyleSheet(f"QDialog {{ background: {colors['bg']}; }}")
    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(24, 20, 24, 16)
    layout.setSpacing(10)

    icon_path = os.path.join(install_dir, "static", "icons", "icon-192.png")
    pm = QPixmap(icon_path) if os.path.isfile(icon_path) else QPixmap()
    if not pm.isNull():
        ic = QLabel()
        ic.setPixmap(pm.scaled(72, 72, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation))
        ic.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(ic)

    label = QLabel(about_html(colors, _app_version(install_dir)))
    label.setOpenExternalLinks(True)   # links open in the default browser
    label.setWordWrap(True)
    label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
    layout.addWidget(label)

    close_btn = QPushButton("Close")
    close_btn.setDefault(True)
    close_btn.clicked.connect(dlg.accept)
    row = QHBoxLayout()
    row.addStretch(1)
    row.addWidget(close_btn)
    row.addStretch(1)
    layout.addLayout(row)
    return dlg


def show_about_dialog(parent, install_dir):
    """Theme-aware About dialog: icon, name, version, description, copyright,
    license, the AGPL no-warranty notice, and Website / Report-an-issue links."""
    build_about_dialog(parent, install_dir).exec()
