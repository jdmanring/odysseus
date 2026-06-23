from pathlib import Path

_CSS = Path("static/style.css").read_text(encoding="utf-8")


def _block(selector: str, window: int = 500) -> str:
    idx = _CSS.index(selector)
    return _CSS[idx: idx + window]




# P6 — content-visibility: auto added to remaining list item selectors

def test_memory_item_content_visibility():
    assert "content-visibility: auto" in _block(".memory-item {")


def test_memory_item_contain_intrinsic_size():
    assert "contain-intrinsic-size" in _block(".memory-item {")


def test_email_item_content_visibility():
    assert "content-visibility: auto" in _block(".email-item {")


def test_email_item_contain_intrinsic_size():
    assert "contain-intrinsic-size" in _block(".email-item {")


def test_doclib_card_content_visibility():
    # Use the exact base rule (context selectors like .doclib-just-opened > .doclib-card
    # appear earlier in the file and would match first).
    idx = _CSS.index("\n.doclib-card {")
    assert "content-visibility: auto" in _CSS[idx: idx + 500]


def test_doclib_card_contain_intrinsic_size():
    idx = _CSS.index("\n.doclib-card {")
    assert "contain-intrinsic-size" in _CSS[idx: idx + 500]


def test_task_run_item_content_visibility():
    assert "content-visibility: auto" in _block(".task-run-item {")


def test_task_run_item_contain_intrinsic_size():
    assert "contain-intrinsic-size" in _block(".task-run-item {")


# P7 — visual suppressions reverted

def test_hover_suppression_comment_removed():
    # The "Suppress paint-inducing background/border-color" comment was the
    # marker for the incorrectly-suppressed .memory-item:hover rule.
    assert "Suppress paint-inducing background/border-color" not in _CSS


def test_memory_list_action_buttons_opacity_suppression_removed():
    # opacity: 1 / transition: none suppression on .memory-item-actions removed.
    assert "#memory-list .memory-item-actions {\n  opacity: 1" not in _CSS


def test_memory_list_menu_btn_suppression_removed():
    # The opacity:1 / transition:none block on .memory-menu-btn was removed.
    assert "#memory-list .memory-menu-btn {\n  opacity: 1" not in _CSS


def test_memory_list_item_transition_preserved():
    # The transition: opacity 0.15s on #memory-list .memory-item must be kept —
    # it eliminates multi-frame background/border-color tiles while preserving
    # opacity transitions (compositor-promoted, zero raster cost).
    assert "transition: opacity 0.15s" in _block("#memory-list .memory-item {", window=800)
