"""
Regression tests for the Brain panel memory list event listener leak fix.

Three distinct garbage sources were addressed:

1. document.addEventListener accumulation:
   renderMemoryList() was adding one document-level click listener per memory
   item per render pass, with { once: false }. 50 items x 10 renders = 500
   never-removed listeners, each holding a closure over a dropdown DOM element.

2. No cleanup on re-render:
   memoryList.innerHTML = '' destroyed old item DOM nodes but their listener
   closures remained in memory until the GC ran (which Qt never triggers).
   An AbortController released all item listeners before clearing the list.

3. Animation runs when panel is hidden:
   ::after sweep animations continued when #memory-modal got .hidden, keeping
   compositor tile allocations alive. CSS animation-play-state: paused fixes this.
"""

import re
from pathlib import Path

_JS_PATH = Path(__file__).resolve().parents[1] / "static" / "js" / "memory.js"
_MM_PATH = Path(__file__).resolve().parents[1] / "static" / "js" / "modalManager.js"
_CSS_PATH = Path(__file__).resolve().parents[1] / "static" / "style.css"


def _js() -> str:
    return _JS_PATH.read_text(encoding="utf-8")


def _mm() -> str:
    return _MM_PATH.read_text(encoding="utf-8")


def _css() -> str:
    return _CSS_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# AbortController infrastructure
# ---------------------------------------------------------------------------

def test_list_abort_ctrl_declared():
    """Module must declare _listAbortCtrl for cross-render listener cleanup."""
    assert "_listAbortCtrl" in _js()


def test_abort_called_before_render():
    """renderMemoryList must abort the previous controller before populating."""
    js = _js()
    idx = js.index("export function renderMemoryList()")
    body = js[idx:idx + 800]
    assert "_listAbortCtrl.abort()" in body


def test_new_abort_controller_created_each_render():
    """A fresh AbortController must be created each render pass."""
    js = _js()
    idx = js.index("export function renderMemoryList()")
    body = js[idx:idx + 800]
    assert "new AbortController()" in body


def test_signal_extracted_for_listeners():
    """The signal is extracted from the controller for use in listeners."""
    js = _js()
    idx = js.index("export function renderMemoryList()")
    body = js[idx:idx + 800]
    assert "_sig = _listAbortCtrl.signal" in body


# ---------------------------------------------------------------------------
# document.addEventListener fix
# ---------------------------------------------------------------------------

def test_document_listener_is_once_true():
    """
    The document click listener that closes the dropdown must use once: true.
    once: false (the original bug) caused the listener to persist forever.
    """
    js = _js()
    assert "{ once: true" in js
    # The old pattern must not exist
    assert "{ once: false }" not in js


def test_document_listener_inside_menuBtn_click():
    """
    The outside-click close handler must be inside the menuBtn click handler,
    not at the forEach level where it ran once per item per render.
    """
    js = _js()
    # Use the last occurrence of document.addEventListener('click' in the file
    # — the first occurrence is the sort-picker handler at module init.
    doc_idx = js.rindex("document.addEventListener('click'")
    # It must appear before the long-press block ('pointerdown') that follows
    # the end of the menuBtn click handler closure.
    lp_idx = js.rindex("item.addEventListener('pointerdown'")
    assert doc_idx < lp_idx, (
        "document.addEventListener('click') must appear inside the menuBtn "
        "click handler, before the long-press pointerdown block"
    )
    # The once: true option must be in the same listener call
    near = js[doc_idx:doc_idx + 200]
    assert "once: true" in near


def test_document_listener_has_signal():
    """The outside-click close handler must carry the render-pass signal."""
    js = _js()
    doc_idx = js.rindex("document.addEventListener('click'")
    near = js[doc_idx:doc_idx + 200]
    assert "signal: _sig" in near or "_sig" in near


# ---------------------------------------------------------------------------
# Modal close cleanup
# ---------------------------------------------------------------------------

def test_modal_close_cleanup_present():
    """DOMContentLoaded must observe memory-modal for the hidden class."""
    js = _js()
    assert "memory-modal" in js
    assert "_memModal.classList.contains('hidden')" in js


def test_modal_close_does_not_abort_controller():
    """
    The modal close handler must NOT abort _listAbortCtrl.

    Aborting on close would leave DOM items without event handlers until the
    next memory-refresh triggers renderMemoryList() — because memory.js has no
    odysseus:modal-opened listener. The abort belongs at the START of
    renderMemoryList() (verified by test_abort_called_before_render), immediately
    before innerHTML is cleared.
    """
    js = _js()
    idx = js.index("_memModal.classList.contains('hidden')")
    block = js[idx:idx + 400]
    assert "_listAbortCtrl.abort()" not in block


def test_modal_close_triggers_gc():
    """Cleanup on modal close must trigger GC when available."""
    js = _js()
    idx = js.index("_memModal.classList.contains('hidden')")
    block = js[idx:idx + 300]
    assert "typeof gc" in block


def test_modal_close_closes_dropdown():
    """Cleanup on modal close must remove any open dropdown."""
    js = _js()
    idx = js.index("_memModal.classList.contains('hidden')")
    block = js[idx:idx + 300]
    assert "_closeActiveDropdown()" in block


# ---------------------------------------------------------------------------
# modalManager.js: modal-closed event
# ---------------------------------------------------------------------------

def test_modal_closed_event_emitted():
    """modalManager must dispatch odysseus:modal-closed when a modal hides."""
    mm = _mm()
    assert "odysseus:modal-closed" in mm


def test_modal_closed_fires_on_hide_transition():
    """The closed event must fire when visibility transitions from true to false."""
    mm = _mm()
    assert "_emitModalClosed" in mm
    # Must be called when !vis && _mmAutoStackLast (hide transition)
    idx = mm.index("!vis && _modalEl._mmAutoStackLast")
    block = mm[idx:idx + 200]
    assert "_emitModalClosed" in block


# ---------------------------------------------------------------------------
# CSS: animation paused when modal hidden
# ---------------------------------------------------------------------------

def test_animation_paused_when_modal_hidden():
    """::after animation must be paused when #memory-modal has .hidden."""
    css = _css()
    assert "#memory-modal.hidden #memory-list .memory-item::after" in css
    idx = css.index("#memory-modal.hidden #memory-list .memory-item::after")
    block = css[idx:idx + 200]
    assert "animation-play-state: paused" in block
