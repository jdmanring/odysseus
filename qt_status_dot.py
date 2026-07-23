"""Colored status-dot icons for the desktop-wrapper tray menus.

Qt-only, shared by qt_wrapper.py and windows_wrapper.py (macOS colours its dot
with an emoji in the rumps menu title instead — see mac_tray_helper.py).

The tray status line is a *disabled* menu action so it reads as a label, not a
button. Qt would desaturate an icon set on a disabled action, so each icon
carries the SAME coloured pixmap for the Disabled mode explicitly — that keeps
the dot vivid green/red instead of a washed-out grey. Green = server running,
red = stopped, amber = a transitional/degraded state (restarting, not
responding).
"""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QBrush

# GitHub-ish status colours; legible on both dark and light menu backgrounds.
_COLORS = {
    "running": "#3fb950",  # green
    "stopped": "#f85149",  # red
    "busy": "#d29922",     # amber — restarting / not responding
}

_cache = {}


def status_dot(state, px=11):
    """Return a cached QIcon of a filled circle in the state's colour. Requires
    a running QGuiApplication (call it while building/refreshing the menu, not
    at import). Unknown states fall back to amber."""
    key = (state, px)
    cached = _cache.get(key)
    if cached is not None:
        return cached
    color = QColor(_COLORS.get(state, _COLORS["busy"]))
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(color))
    m = 1  # 1px inset so the antialiased edge isn't clipped
    p.drawEllipse(m, m, px - 2 * m, px - 2 * m)
    p.end()
    icon = QIcon()
    icon.addPixmap(pm, QIcon.Mode.Normal)
    icon.addPixmap(pm, QIcon.Mode.Disabled)  # keep colour on the disabled action
    _cache[key] = icon
    return icon
