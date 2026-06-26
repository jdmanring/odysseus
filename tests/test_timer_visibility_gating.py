"""Visibility-gating of perpetual background timers (#118, audit D1/D2).

Background timers should not do work / wake the app while the tab is hidden.
modalManager pauses its 1s auto-wire scan when hidden (resumes on return);
the email-unread and tasks-notification polls early-return when not visible,
matching the pattern calendar.js already uses. Static assertions on source.
"""
from pathlib import Path

_JS = Path(__file__).resolve().parents[1] / "static" / "js"
_MODAL = (_JS / "modalManager.js").read_text(encoding="utf-8")
_EMAIL = (_JS / "emailInbox.js").read_text(encoding="utf-8")
_TASKS = (_JS / "tasks.js").read_text(encoding="utf-8")


def test_modal_scan_pauses_when_hidden():
    # Pause the interval on hide, resume on show — not just a no-op tick.
    assert "addEventListener('visibilitychange'" in _MODAL
    assert "clearInterval(_scanTimer)" in _MODAL
    assert "_scanTimer = setInterval(_scanAndWire, 1000)" in _MODAL


def test_email_poll_gated_on_visibility():
    block = _EMAIL[_EMAIL.index("async function _refreshUnreadCount"):][:400]
    assert "document.visibilityState !== 'visible'" in block
    assert "return" in block


def test_tasks_poll_gated_on_visibility():
    block = _TASKS[_TASKS.index("async function _pollTaskNotifications"):][:300]
    assert "document.visibilityState !== 'visible'" in block
    assert "return" in block
