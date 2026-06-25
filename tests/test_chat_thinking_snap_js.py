"""Source-text guards for snap-to-bottom hardening across the Thinking-box
transition (jdmanring#104).

During streaming, the ".agent-thinking-dots" box appears (grow), is removed
(shrink), then the real message renders (grow). The throttled smooth scroll
dropped the re-snap inside that window. scrollHistorySettle() pins the view to
the bottom every frame for a short window across the transition, gated on
auto-follow, and _removeThinkingSpinner triggers it.
"""
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_UI = (_REPO / "static/js/ui.js").read_text(encoding="utf-8")
_CHAT = (_REPO / "static/js/chat.js").read_text(encoding="utf-8")


def _settle_body() -> str:
    start = _UI.index("export function scrollHistorySettle(")
    end = _UI.index("\nexport ", start + 1)
    return _UI[start:end]


def test_scroll_history_settle_exists_and_exported():
    assert "export function scrollHistorySettle(" in _UI
    # Present in the default-export object so uiModule.scrollHistorySettle works.
    assert "scrollHistorySettle," in _UI


def test_settle_is_gated_on_auto_follow():
    # A user who scrolled up must never be yanked down.
    body = _settle_body()
    assert "if (!autoScrollEnabled) return;" in body


def test_settle_snaps_to_bottom_each_frame_within_a_bounded_window():
    body = _settle_body()
    # Snaps to the current bottom (tracks the moving bottom).
    assert "_scrollBox.scrollTop = _scrollBox.scrollHeight - _scrollBox.clientHeight" in body
    # Bounded by a deadline, not an unbounded loop.
    assert "_settleUntil" in body
    assert "requestAnimationFrame(step)" in body


def test_remove_thinking_spinner_triggers_settle():
    # The shrink (box removal) must start the settle so the subsequent message
    # grow is followed. Anchor on the real body (which removes the box), not the
    # `let _removeThinkingSpinner = () => {};` forward-declaration stub.
    idx = _CHAT.index("const el = document.querySelector('.agent-thinking-dots')")
    block = _CHAT[idx:idx + 600]
    assert "el.remove()" in block
    assert "uiModule.scrollHistorySettle()" in block
