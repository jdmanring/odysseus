"""Static validation of the Cookbook Running-tab Launch-button reconciliation.

The upstream merge kept the fork's aria2c download card but dropped upstream's
"Launch" button (one-click serve of a finished download) from the card header —
leaving its click handler wired to a `.cookbook-task-serve-btn` element that was
never rendered, so the feature silently no-op'd. This re-renders the button,
gated by _canLaunchDownloadedTask, labelled via _taskDisplayName.

cookbookRunning.js is an ES module coupled to the app bootstrap (initRunning DI
runs in cookbook.js's entry order; importing it in isolation hits a circular-
import TDZ), so — like the other browser-coupled *_js.py checks — this analyses
the source text to lock the render↔handler contract that the merge broke.
"""
import re
from pathlib import Path

_SRC = (Path(__file__).resolve().parent.parent / "static" / "js" / "cookbookRunning.js").read_text(encoding="utf-8")

# The card render — the innerHTML template that builds each task card (from the
# innerHTML assignment to the terminating backtick + semicolon).
_CARD_START = _SRC.index("el.innerHTML = `")
_CARD = _SRC[_CARD_START:_SRC.index("`;", _CARD_START) + 2]

_SERVE_BTN_CLASS = "cookbook-task-serve-btn"


def test_helpers_are_defined():
    for fn in ("_taskDisplayName", "_canLaunchDownloadedTask", "_shouldAutoExpandTaskOutput"):
        assert re.search(rf"function {fn}\(", _SRC), fn


def test_launch_button_rendered_and_gated():
    # The button must be emitted in the card, gated on _canLaunchDownloadedTask,
    # carrying the exact class the handler queries.
    assert "_canLaunchDownloadedTask(task) ?" in _CARD
    assert _SERVE_BTN_CLASS in _CARD
    assert ">Launch</span>" in _CARD


def test_launch_button_class_matches_handler_selector():
    # The bug the merge introduced: button HTML present but class != what the
    # handler queries => dead feature. Lock both sides to the same class.
    assert f'querySelector(\'.{_SERVE_BTN_CLASS}\')' in _SRC or \
           f'querySelector(".{_SERVE_BTN_CLASS}")' in _SRC, "handler must query the serve button"
    # Rendered class and queried class are the same literal.
    rendered = f'class="{_SERVE_BTN_CLASS}"'
    assert rendered in _CARD, "card must render the button with the handler's class"


def test_display_name_used_for_card_title():
    assert "esc(_taskDisplayName(task))" in _CARD


def test_download_output_uses_auto_expand():
    # The download (_isDl) branch must respect _shouldAutoExpandTaskOutput so an
    # active/failed download isn't collapsed on mobile.
    assert "!_shouldAutoExpandTaskOutput(task)" in _CARD


def test_launch_gating_predicate_is_finished_download():
    body = _SRC[_SRC.index("function _canLaunchDownloadedTask"):]
    body = body[:body.index("}")]
    assert "type === 'download'" in body
    assert "'done'" in body and "'completed'" in body
    assert "repo_id" in body
