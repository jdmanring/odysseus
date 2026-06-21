# Source-text contract tests for hljsDefer.js (IntersectionObserver-based deferred highlighting).
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SRC  = (_REPO / "static/js/hljsDefer.js").read_text(encoding="utf-8")
_CHAT = (_REPO / "static/js/chat.js").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Observer setup
# ---------------------------------------------------------------------------

def test_single_shared_observer():
    # One observer for the whole module — multiple instances would each hold
    # their own reference set and fragment the unobserve() contract.
    assert _SRC.count("new IntersectionObserver(") == 1


def test_observer_root_margin():
    # 200px lookahead so blocks just above the fold highlight before they scroll in.
    assert "rootMargin: '200px 0px'" in _SRC


def test_unobserve_after_highlight():
    # Each block is observed exactly once; unobserve() on intersection prevents
    # the observer from retaining a reference after highlighting is done.
    obs_pos      = _SRC.index("_obs.observe(")
    unobserve_pos = _SRC.index("_obs.unobserve(")
    assert unobserve_pos > 0
    # unobserve is inside the callback (before observe in source order)
    assert unobserve_pos < obs_pos


def test_already_highlighted_guard():
    # Skip blocks that hljs already processed (.hljs class) to avoid double work.
    assert "classList.contains('hljs')" in _SRC


# ---------------------------------------------------------------------------
# deferHighlight / deferHighlightAll exports
# ---------------------------------------------------------------------------

def test_defer_highlight_exported():
    assert "export function deferHighlight(" in _SRC


def test_defer_highlight_all_exported():
    assert "export function deferHighlightAll(" in _SRC


def test_defer_highlight_all_queries_unhighlighted():
    # Must not re-observe already-highlighted blocks.
    assert "querySelectorAll('pre code:not(.hljs)')" in _SRC


# ---------------------------------------------------------------------------
# forgetNode export — observer cleanup before DOM removal
# ---------------------------------------------------------------------------

def test_forget_node_exported():
    assert "export function forgetNode(" in _SRC


def test_forget_node_unobserves_all_code_blocks():
    # Must cover already-highlighted blocks too (observer may still hold them
    # if the highlight callback hasn't fired yet).
    start = _SRC.index("export function forgetNode(")
    end   = _SRC.index("\n}", start) + 2
    body  = _SRC[start:end]
    assert "querySelectorAll('pre code')" in body
    assert "_obs.unobserve(" in body


def test_forget_node_no_hljs_filter():
    # forgetNode must NOT filter by :not(.hljs) — the observer may still hold
    # a block that was highlighted in the same tick (race between highlight
    # callback and eviction).  Unobserving an already-unobserved node is a no-op.
    start = _SRC.index("export function forgetNode(")
    end   = _SRC.index("\n}", start) + 2
    body  = _SRC[start:end]
    assert ":not(.hljs)" not in body


# ---------------------------------------------------------------------------
# Window registration in chat.js (bridge to non-module chatHistory.js)
# ---------------------------------------------------------------------------

def test_chat_imports_forget_node():
    assert "forgetNode" in _CHAT
    assert "hljsDefer.js" in _CHAT


def test_chat_registers_forget_node_on_window():
    assert "window.hljsDeferForgetNode" in _CHAT


def test_chat_registers_both_globals_together():
    # Both globals set in the same init block — order doesn't matter but they
    # must both be present so chatHistory.js can guard on either.
    hl_pos  = _CHAT.index("window.hljsDeferHighlightAll")
    fgt_pos = _CHAT.index("window.hljsDeferForgetNode")
    assert abs(hl_pos - fgt_pos) < 200, "globals should be registered together at init"
