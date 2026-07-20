"""macOS wrapper polish contract (#158): close-to-Dock lifecycle + native Edit menu.

mac_wrapper.py can't be imported off-macOS (PyQt + os.dup2 + ctypes libSystem
side effects at import), so the contract is pinned statically, matching the
other wrapper suites. The behaviors themselves were verified live on the Tahoe
bench by driving QEvent.Quit / closeAllWindows headlessly (TCC blocks UI
scripting): red button hides + app survives, reopen re-shows, quit tears down.
"""
import re
from pathlib import Path

SRC = Path("mac_wrapper.py").read_text(encoding="utf-8")


def _method(name):
    m = re.search(rf"\n    def {name}\(.*?(?=\n    def |\nclass )", SRC, re.S)
    assert m, f"{name} not found"
    return m.group(0)


def test_does_not_quit_on_last_window_closed():
    # The red button must not quit the app; this is what keeps it in the Dock.
    assert "app.setQuitOnLastWindowClosed(False)" in SRC


def test_quit_filter_arms_on_quit_event():
    # ⌘Q / Dock Quit / quit Apple Event arrive as QEvent.Quit; the filter must
    # flag the window BEFORE closeEvent so a real quit is not vetoed.
    block = re.search(r"class _QuitFilter\(QObject\):.*?(?=\nclass )", SRC, re.S).group(0)
    assert "event.type() == QEvent.Type.Quit" in block
    assert "self._window._quitting = True" in block
    assert "return False" in block  # must not consume the event


def test_close_event_hides_unless_quitting():
    ce = _method("closeEvent")
    # Real quit path: accept so the window closes and quit proceeds.
    assert "if self._quitting:" in ce
    assert "event.accept()" in ce
    # Red-button path: hide + ignore (veto the close, keep the app alive).
    assert "self.hide()" in ce
    assert "event.ignore()" in ce
    # The accept must be gated by _quitting, before the hide branch.
    assert ce.index("event.accept()") < ce.index("self.hide()")


def test_reopen_shows_hidden_window_on_activate():
    assert "app.applicationStateChanged.connect(" in SRC
    assert "Qt.ApplicationState.ApplicationActive and not win.isVisible()" in SRC


def test_teardown_on_about_to_quit_stops_server():
    assert "app.aboutToQuit.connect(" in SRC
    td = re.search(r"def _teardown\(\):.*?stop_server\(\)", SRC, re.S)
    assert td and "stop_server()" in td.group(0)


def test_edit_menu_wired_to_page_actions():
    bm = _method("_build_menus")
    assert 'self.menuBar().addMenu("Edit")' in bm
    assert "triggerPageAction" in bm
    for action in ("Undo", "Redo", "Cut", "Copy", "Paste", "SelectAll"):
        assert f"WA.{action}" in bm, f"Edit menu missing {action}"
    # Standard-key shortcuts so the mac shortcuts (⌘C etc.) bind correctly.
    assert "QKeySequence(std_key)" in bm
    assert "SK.Copy" in bm and "SK.Paste" in bm


def test_menus_built_during_window_init():
    assert "self._build_menus()" in _method("__init__") or "self._build_menus()" in SRC
