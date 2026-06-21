# Static-analysis tests for WeakRef usage in continue-button click handlers in chat.js.
# Three continue buttons capture the message holder in their closures; without WeakRef
# the closure is a strong GC root that prevents evicted nodes from being collected.
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SRC  = (_REPO / "static/js/chat.js").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Helpers — extract each button block
# ---------------------------------------------------------------------------

def _interrupted_block() -> str:
    """The 'message interrupted' continue button (inside the holder's subtree)."""
    marker = "className = 'continue-btn';\n        continueBtn.title = 'Continue';"
    start  = _SRC.index(marker)
    end    = _SRC.index("stoppedIndicator.appendChild(continueBtn)", start) + 45
    return _SRC[start:end]


def _step_limit_block() -> str:
    """The step-limit continue button (appended to _chatBox — live DOM after eviction)."""
    marker = "className = 'continue-btn';\n                  contBtn.title = 'Continue the task';"
    start  = _SRC.index(marker)
    end    = _SRC.index("note.appendChild(contBtn)", start) + 25
    return _SRC[start:end]


def _catch_block() -> str:
    """The catch-block interrupted continue button (inside the holder's subtree)."""
    marker = "className = 'continue-btn';\n            continueBtn.title = 'Continue';"
    start  = _SRC.index(marker)
    end    = _SRC.index("stoppedIndicator.appendChild(continueBtn)", start) + 45
    return _SRC[start:end]


# ---------------------------------------------------------------------------
# WeakRef creation — all three sites must use WeakRef
# ---------------------------------------------------------------------------

def test_interrupted_btn_uses_weakref():
    assert "new WeakRef(" in _interrupted_block()


def test_step_limit_btn_uses_weakref():
    # This is the confirmed GC-root case: button lives in _chatBox after holder eviction.
    assert "new WeakRef(" in _step_limit_block()


def test_catch_block_btn_uses_weakref():
    assert "new WeakRef(" in _catch_block()


# ---------------------------------------------------------------------------
# WeakRef deref + null guard — must check before using the reference
# ---------------------------------------------------------------------------

def test_interrupted_btn_derefs_weakref():
    assert ".deref()" in _interrupted_block()


def test_step_limit_btn_derefs_weakref():
    assert ".deref()" in _step_limit_block()


def test_catch_block_btn_derefs_weakref():
    assert ".deref()" in _catch_block()


def test_interrupted_btn_guards_null():
    block = _interrupted_block()
    # Guard must appear before _pendingContinue assignment.
    guard_pos    = block.index("if (!")
    continue_pos = block.index("_pendingContinue =")
    assert guard_pos < continue_pos, "null guard must precede _pendingContinue assignment"


def test_step_limit_btn_guards_null():
    block = _step_limit_block()
    guard_pos    = block.index("if (!")
    continue_pos = block.index("_pendingContinue =")
    assert guard_pos < continue_pos, "null guard must precede _pendingContinue assignment"


def test_catch_block_btn_guards_null():
    block = _catch_block()
    guard_pos    = block.index("if (!")
    continue_pos = block.index("_pendingContinue =")
    assert guard_pos < continue_pos, "null guard must precede _pendingContinue assignment"
