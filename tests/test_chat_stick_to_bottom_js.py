"""Source-text guards for the stick-to-bottom mechanism (jdmanring#104,
supersedes the earlier scrollHistorySettle approach).

A single observer is the source of truth for keeping the chat pinned to the
bottom: it re-pins on any geometry change while the view is pinned, covering
both late async growth (image decode, syntax-highlight reflow, the final
streamed block) and the mid-stream "Thinking" box shrink/grow. These assert the
invariants that make it correct; they prove the code's shape, not the runtime
behaviour (that needs an in-app before/after — see chat-scroll-research.md).
"""
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_UI = (_REPO / "static/js/ui.js").read_text(encoding="utf-8")


def _stick_body() -> str:
    start = _UI.index("function _initStickToBottom(")
    end = _UI.index("\nif (document.readyState", start)
    return _UI[start:end]


def test_is_pinned_flag_exists():
    # The real auto-follow intent signal (autoScrollEnabled is a dead gate).
    assert "let isPinned = true;" in _UI


def test_pin_threshold_matches_follow_loop():
    # isPinned must use the same distance the follow loop bails at, or the lerp's
    # transient gaps would flip it false mid-stream and break following.
    assert "function _followDistance(box) { return Math.max(300, box.clientHeight * 1.5); }" in _UI
    body = _stick_body()
    assert "<= _followDistance(box)" in body


def test_pin_updated_on_scroll():
    body = _stick_body()
    assert "box.addEventListener('scroll'" in body
    assert "box.scrollHeight - box.scrollTop - box.clientHeight" in body


def test_repin_gated_on_pinned():
    # A user who scrolled up must never be yanked down.
    body = _stick_body()
    assert "if (!isPinned" in body


def test_repin_defers_only_while_loop_animating():
    # Defer on _scrollRafId (active lerp) only — NOT the 500ms throttle window —
    # so the observer still catches the Thinking-box transition during a pause.
    body = _stick_body()
    assert "_scrollRafId" in body
    assert "_scrollThrottleTimer" not in body


def test_repin_snaps_to_bottom_coalesced_via_raf():
    body = _stick_body()
    assert "requestAnimationFrame(" in body
    assert "box.scrollTop = box.scrollHeight - box.clientHeight" in body


def test_uses_mutation_and_resize_observers():
    # MutationObserver for DOM-driven growth (direct children, no wrapper);
    # per-child ResizeObserver for pure layout growth (image decode).
    body = _stick_body()
    assert "new MutationObserver(" in body
    assert "new ResizeObserver(" in body
    assert "ro.observe(n)" in body


def test_settle_mechanism_retired():
    # scrollHistorySettle was folded into the observer; it must not linger.
    assert "scrollHistorySettle" not in _UI
