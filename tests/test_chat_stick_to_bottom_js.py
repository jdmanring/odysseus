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


def test_unpin_is_direction_based_not_distance_based():
    # Content growth never decreases scrollTop — only the user scrolling up
    # does. Direction disambiguates "lerp lagging a growing stream" from
    # "user scrolled away", which no distance threshold can: one big enough
    # to absorb lerp lag (~1.5 viewports) was unescapable by wheel (#145).
    assert "_followDistance" not in _UI, "distance-threshold unpin must be gone"
    body = _stick_body()
    assert "box.scrollTop < _lastScrollTop" in body
    assert "isPinned = false" in body


def test_upward_jump_within_epsilon_cannot_unpin():
    # Prune/eviction scroll compensation lands back at the bottom; an upward
    # scrollTop jump that stays within REPIN_DISTANCE must not unpin.
    body = _stick_body()
    assert "dist > REPIN_DISTANCE" in body


def test_wheel_up_unpins_before_scroll_event():
    body = _stick_body()
    assert "box.addEventListener('wheel'" in body
    assert "e.deltaY < 0" in body


def test_repin_when_user_returns_to_bottom():
    body = _stick_body()
    assert "dist <= REPIN_DISTANCE" in body
    assert "isPinned = true" in body


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


def test_container_disables_native_scroll_anchoring():
    # Chromium scroll anchoring adjusts scrollTop invisibly to JS on content
    # changes and fights the pin logic in both directions (bounced pinned
    # follows; dragged unpinned views). The scroller must opt out; the
    # observer + manual compensation own anchoring.
    import pathlib
    css = (pathlib.Path(__file__).resolve().parent.parent / "static/style.css").read_text(encoding="utf-8")
    start = css.index(".chat-history {")
    block = css[start:css.index("}", start)]
    assert "overflow-anchor: none" in block
