"""Static validation of streamingRenderer.js structural contracts.

streamingRenderer.js is browser-coupled (uses DOM) and cannot be imported
in pytest. These checks analyse the source text to lock in the structural
contracts for deferred hljs highlighting in freeze():

- freeze() inserts nodes into the live DOM before observing them, so
  IntersectionObserver can measure viewport distance and defer hljs span
  allocation for off-screen code blocks.
- fullRender() (degraded fallback) retains immediate highlight.

Root: docs/fork/memory-explosion-research.md (Session 3 deep analysis)
"""

from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SRC  = (_REPO / "static/js/streamingRenderer.js").read_text(encoding="utf-8")


def _freeze_body() -> str:
    start = _SRC.index("function freeze(")
    end   = _SRC.index("\n  }", start) + 4
    return _SRC[start:end]


def _full_render_body() -> str:
    start = _SRC.index("function fullRender(")
    end   = _SRC.index("\n  }", start) + 4
    return _SRC[start:end]


# ---------------------------------------------------------------------------
# Deferred hljs highlighting in freeze()
# ---------------------------------------------------------------------------

def test_freeze_imports_defer_highlight():
    # hljsDefer.js must be imported so deferHighlight is in scope.
    assert "hljsDefer.js" in _SRC


def test_freeze_collects_code_blocks_before_insert():
    # Code block refs must be captured while still in holder (before DOM move),
    # so IntersectionObserver gets live nodes after insertion.
    body = _freeze_body()
    assert "querySelectorAll('pre code')" in body or 'querySelectorAll("pre code")' in body


def test_freeze_inserts_before_observing():
    # Insertion (insertBefore) must come before the deferHighlight loop so the
    # observer can measure viewport position on live DOM nodes.
    body = _freeze_body()
    insert_pos  = body.index("insertBefore")
    observe_pos = body.index("deferHighlight")
    assert insert_pos < observe_pos, "insertBefore must precede deferHighlight in freeze()"


def test_freeze_no_immediate_highlight():
    # The old highlight(holder) call must not appear in freeze() — we no longer
    # run hljs synchronously on a detached fragment.
    body = _freeze_body()
    assert "highlight(holder)" not in body
    assert "highlightElement" not in body


def test_full_render_keeps_immediate_highlight():
    # fullRender() is the degraded fallback — it must still highlight immediately
    # since we can't rely on observer firing in an already-broken renderer state.
    body = _full_render_body()
    assert "highlightElement" in body
