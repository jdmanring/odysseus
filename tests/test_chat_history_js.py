"""Static validation of chatHistory.js — DOM virtualization for #chat-history.

chatHistory.js is browser-coupled (IntersectionObserver, MutationObserver, DOM
APIs) and cannot be imported in pytest.  Following the pattern established by
test_dialog_aria.py and test_document_editor_scroll.py, these checks analyse
the source text to lock in the structural contracts that matter:

  Phase 1  load-time windowing   — renders last WINDOW_SIZE messages on load,
                                   loads older batches via IntersectionObserver
  Phase 2  live pruning          — caps DOM children with MutationObserver,
                                   injects a height-matched spacer
  Phase 3  bidirectional pruning — caps historical *messages* in DOM during
                                   scroll-up via BIDI_MSG_CAP (message count,
                                   not DOM node count — agent messages inflate
                                   node count unpredictably); restores via
                                   scroll event listener (NOT IntersectionObserver
                                   — IO fires immediately after prune, defeating
                                   the pruning). _loadNewer still uses BIDI_CAP
                                   (DOM nodes) for the symmetric top prune.

Manual verification required before the upstream PR:
  1. Load a session with 60+ messages — only the last 50 should be in the DOM.
  2. Scroll to the top — sentinel "↑ N earlier messages" should load next batch.
  3. Scroll position must not jump when older messages are prepended.
  4. Run a long agent session (30+ rounds) — DOM child count must stay ≤ 80.
  5. Scroll all the way up through a 200+ message session (ideally an agent session
     with many tool rounds) — historical messages in DOM must stay ≤ 80+25; scroll
     position must NOT jump to the bottom on each batch load.
  6. Scroll back down — pruned historical messages must reload as you scroll.
"""

import re
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SRC  = (_REPO / "static/js/chatHistory.js").read_text(encoding="utf-8")
_SESS = (_REPO / "static/js/sessions.js").read_text(encoding="utf-8")
_HTML = (_REPO / "static/index.html").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Module structure
# ---------------------------------------------------------------------------

def test_is_iife_not_es_module():
    assert "(function () {" in _SRC or "(function(){" in _SRC
    assert "export " not in _SRC
    assert 'type="module"' not in _SRC


def test_sets_window_chatHistory_singleton():
    assert "window.chatHistory = new MessageWindow" in _SRC


def test_index_html_loads_script_before_modules():
    idx_chat    = _HTML.index("chatHistory.js")
    idx_module  = _HTML.index('type="module"')
    assert idx_chat < idx_module, (
        "chatHistory.js must be loaded before the first <script type=\"module\">"
    )


# ---------------------------------------------------------------------------
# Constants — values are load-tested at runtime, structure locked here
# ---------------------------------------------------------------------------

def test_window_size_constant_defined():
    assert "WINDOW_SIZE" in _SRC


def test_batch_size_constant_defined():
    assert "BATCH_SIZE" in _SRC


def test_prune_at_constant_defined():
    assert "PRUNE_AT" in _SRC


def test_prune_count_constant_defined():
    assert "PRUNE_COUNT" in _SRC


def test_bidi_cap_constant_defined():
    # BIDI_CAP (DOM node count) is still used by _loadNewer for the top prune.
    assert "BIDI_CAP" in _SRC


def test_bidi_msg_cap_constant_defined():
    # BIDI_MSG_CAP (message count) guards Phase 3 in _loadOlder.
    # Message-count cap is immune to per-message DOM child inflation in agent sessions.
    assert "BIDI_MSG_CAP" in _SRC


def test_window_size_is_50():
    m = re.search(r"var WINDOW_SIZE\s*=\s*(\d+)", _SRC)
    assert m, "WINDOW_SIZE not found"
    assert int(m.group(1)) == 50


def test_bidi_cap_exceeds_window_size():
    ws = int(re.search(r"var WINDOW_SIZE\s*=\s*(\d+)", _SRC).group(1))
    bc = int(re.search(r"var BIDI_CAP\s*=\s*(\d+)", _SRC).group(1))
    assert bc > ws, "BIDI_CAP must exceed WINDOW_SIZE"


def test_prune_at_exceeds_window_size():
    ws = int(re.search(r"var WINDOW_SIZE\s*=\s*(\d+)", _SRC).group(1))
    pa = int(re.search(r"var PRUNE_AT\s*=\s*(\d+)", _SRC).group(1))
    assert pa > ws, "PRUNE_AT must be greater than WINDOW_SIZE to allow headroom"


# ---------------------------------------------------------------------------
# MessageWindow — required prototype methods
# ---------------------------------------------------------------------------

def test_message_window_constructor_exists():
    assert "function MessageWindow" in _SRC


def test_prototype_load():
    assert "MessageWindow.prototype.load" in _SRC


def test_prototype_reset():
    assert "MessageWindow.prototype.reset" in _SRC


def test_prototype_render_tail():
    assert "MessageWindow.prototype._renderTail" in _SRC


def test_prototype_attach_sentinel():
    assert "MessageWindow.prototype._attachSentinel" in _SRC


def test_prototype_detach_sentinel():
    assert "MessageWindow.prototype._detachSentinel" in _SRC


def test_prototype_attach_bottom_sentinel():
    assert "MessageWindow.prototype._attachBottomSentinel" in _SRC


def test_prototype_detach_bottom_sentinel():
    assert "MessageWindow.prototype._detachBottomSentinel" in _SRC


def test_prototype_load_older():
    assert "MessageWindow.prototype._loadOlder" in _SRC


def test_prototype_load_newer():
    assert "MessageWindow.prototype._loadNewer" in _SRC


def test_prototype_init_mut_obs():
    assert "MessageWindow.prototype._initMutObs" in _SRC


def test_prototype_init_scroll_listener():
    assert "MessageWindow.prototype._initScrollListener" in _SRC


def test_prototype_maybe_prune():
    assert "MessageWindow.prototype._maybePrune" in _SRC


def test_prototype_prune_top():
    assert "MessageWindow.prototype._pruneTop" in _SRC


def test_prototype_prune_bottom():
    assert "MessageWindow.prototype._pruneBottom" in _SRC


def test_prototype_live_child_count():
    assert "MessageWindow.prototype._liveChildCount" in _SRC


def test_prototype_hist_child_count():
    assert "MessageWindow.prototype._histChildCount" in _SRC


# ---------------------------------------------------------------------------
# Phase 1 — sentinel & scroll-position preservation
# ---------------------------------------------------------------------------

def test_sentinel_has_class_name():
    assert "chat-history-sentinel" in _SRC


def test_bottom_sentinel_has_class_name():
    assert "chat-history-bottom-sentinel" in _SRC


def test_scroll_listener_drives_bidi_load():
    # Phase 3 downward loading must use a scroll event, NOT IntersectionObserver.
    # IO fires on any visibility change including the one _pruneBottom() causes
    # (content removed below makes sentinel visible immediately), which would
    # restore pruned content immediately — defeating the whole pruning step.
    sl = _SRC[_SRC.index("MessageWindow.prototype._initScrollListener"):]
    sl = sl[:sl.index("MessageWindow.prototype._loadOlder")]
    assert "addEventListener" in sl and "scroll" in sl, (
        "_initScrollListener must add a 'scroll' event listener"
    )
    assert "_loadNewer" in sl, (
        "_initScrollListener must call _loadNewer when bottom sentinel is near view"
    )


def test_hist_sep_has_class_name():
    assert "chat-history-sep" in _SRC


def test_sentinel_label_shows_count():
    assert "earlier messages" in _SRC


def test_uses_intersection_observer():
    assert "IntersectionObserver" in _SRC


def test_load_older_preserves_scroll_position():
    assert "scrollHeight" in _SRC
    assert "scrollTop" in _SRC


def test_load_older_uses_document_fragment():
    assert "createDocumentFragment" in _SRC


def test_load_older_inserts_before_existing_content():
    assert "insertBefore" in _SRC


def test_load_older_re_highlights_code_blocks():
    assert "hljs" in _SRC
    assert "highlightElement" in _SRC


def test_start_idx_updated_after_load_older():
    assert "this._startIdx = from" in _SRC


def test_end_idx_tracked():
    assert "this._endIdx" in _SRC


def test_load_older_captures_all_children_not_just_last():
    assert "children.length" in _SRC
    assert "snap" in _SRC


def test_render_tail_inserts_hist_sep():
    rt = _SRC[_SRC.index("MessageWindow.prototype._renderTail"):]
    rt = rt[:rt.index("MessageWindow.prototype._attachSentinel")]
    assert "chat-history-sep" in rt, "_renderTail must insert the hist/live separator"


# ---------------------------------------------------------------------------
# _loading guard — must use rAF, not synchronous release
# ---------------------------------------------------------------------------

def test_loading_guard_uses_raf_in_load():
    load_fn = _SRC[_SRC.index("MessageWindow.prototype.load"):]
    load_fn = load_fn[:load_fn.index("MessageWindow.prototype.reset")]
    assert "requestAnimationFrame" in load_fn, (
        "load() must release _loading via rAF, not synchronously"
    )


def test_loading_guard_uses_raf_in_load_older():
    lo = _SRC[_SRC.index("MessageWindow.prototype._loadOlder"):]
    lo = lo[:lo.index("MessageWindow.prototype._loadNewer")]
    assert "requestAnimationFrame" in lo, (
        "_loadOlder must release _loading via rAF"
    )


def test_render_tail_does_not_set_loading():
    rt = _SRC[_SRC.index("MessageWindow.prototype._renderTail"):]
    rt = rt[:rt.index("MessageWindow.prototype._attachSentinel")]
    assert "_loading" not in rt, (
        "_renderTail must not set _loading — load() owns the lock"
    )


# ---------------------------------------------------------------------------
# Phase 2 — scroll-position guard
# ---------------------------------------------------------------------------

def test_maybePrune_checks_scroll_position():
    assert "_isAtBottom" in _SRC


def test_is_at_bottom_method_exists():
    assert "MessageWindow.prototype._isAtBottom" in _SRC


def test_prune_top_updates_start_idx():
    # Implementation uses data-ch-idx to find the highest index pruned,
    # then sets _startIdx = highIdx + 1 (not += removed, which would be
    # wrong for multi-DOM-child messages).
    assert "this._startIdx = highIdx + 1" in _SRC


def test_prune_top_calls_attach_sentinel():
    pt = _SRC[_SRC.index("MessageWindow.prototype._pruneTop"):]
    pt = pt[:pt.index("MessageWindow.prototype._pruneBottom")]
    assert "_attachSentinel" in pt


# ---------------------------------------------------------------------------
# Phase 3 — bidirectional pruning
# ---------------------------------------------------------------------------

def test_load_older_phase3_uses_msg_count():
    # Phase 3 in _loadOlder is guarded by message count, NOT DOM node count.
    # A DOM-node cap (BIDI_CAP) is unsafe for agent sessions: WINDOW_SIZE=50
    # messages can produce 500+ DOM nodes, causing a massive prune on the first
    # _loadOlder() call that collapses scrollHeight and clamps scrollTop to the
    # bottom.  The fix uses (_endIdx - _startIdx) vs BIDI_MSG_CAP instead.
    lo = _SRC[_SRC.index("MessageWindow.prototype._loadOlder"):]
    lo = lo[:lo.index("MessageWindow.prototype._loadNewer")]
    assert "BIDI_MSG_CAP" in lo, (
        "_loadOlder Phase 3 must use BIDI_MSG_CAP (message count) not BIDI_CAP (DOM nodes)"
    )
    assert "_endIdx" in lo and "_startIdx" in lo, (
        "_loadOlder Phase 3 must compute message count as _endIdx - _startIdx"
    )
    assert "_attachBottomSentinel" in lo, (
        "_loadOlder Phase 3 must attach the bottom sentinel after pruning"
    )
    # _histChildCount (DOM node walk) must NOT be used here — it is the wrong
    # unit and was the root cause of the scroll-jump bug.
    assert "_histChildCount" not in lo, (
        "_loadOlder must not use _histChildCount for Phase 3; that was the bug"
    )


def test_prune_bottom_tracks_end_idx():
    # New implementation sets _endIdx = lowestIdx (data-attribute based) rather
    # than decrementing per DOM node, so multi-child messages track correctly.
    pb = _SRC[_SRC.index("MessageWindow.prototype._pruneBottom"):]
    pb = pb[:pb.index("window.chatHistory = new MessageWindow")]
    assert "this._endIdx" in pb, "_pruneBottom must update _endIdx"


def test_prune_bottom_uses_data_ch_idx():
    pb = _SRC[_SRC.index("MessageWindow.prototype._pruneBottom"):]
    pb = pb[:pb.index("window.chatHistory = new MessageWindow")]
    assert "chIdx" in pb, (
        "_pruneBottom must read data-ch-idx for accurate _endIdx tracking "
        "when a single _all entry creates multiple DOM children"
    )


def test_prune_bottom_attaches_bottom_sentinel():
    pb = _SRC[_SRC.index("MessageWindow.prototype._pruneBottom"):]
    pb = pb[:pb.index("window.chatHistory = new MessageWindow")]
    assert "_attachBottomSentinel" in pb


def test_load_newer_updates_end_idx():
    ln = _SRC[_SRC.index("MessageWindow.prototype._loadNewer"):]
    ln = ln[:ln.index("MessageWindow.prototype._initMutObs")]
    assert "this._endIdx" in ln


def test_load_newer_inserts_before_hist_sep():
    ln = _SRC[_SRC.index("MessageWindow.prototype._loadNewer"):]
    ln = ln[:ln.index("MessageWindow.prototype._initMutObs")]
    assert "this._histSep" in ln
    assert "insertBefore" in ln


def test_load_newer_prunes_top_when_over_bidi_cap():
    ln = _SRC[_SRC.index("MessageWindow.prototype._loadNewer"):]
    ln = ln[:ln.index("MessageWindow.prototype._initMutObs")]
    assert "BIDI_CAP" in ln, (
        "_loadNewer must prune from the top when histChildCount > BIDI_CAP, "
        "symmetric with _loadOlder pruning from the bottom"
    )
    assert "_histChildCount" in ln
    assert "_attachSentinel" in ln


def test_load_newer_adjusts_scroll_top_after_top_prune():
    ln = _SRC[_SRC.index("MessageWindow.prototype._loadNewer"):]
    ln = ln[:ln.index("MessageWindow.prototype._initMutObs")]
    assert "scrollTop" in ln, (
        "_loadNewer must compensate scrollTop after removing content from above "
        "the viewport, same technique as _loadOlder"
    )


# ---------------------------------------------------------------------------
# Phase 2 — live pruning
# ---------------------------------------------------------------------------

def test_uses_mutation_observer():
    assert "MutationObserver" in _SRC


def test_mutation_observer_watches_child_list():
    assert "childList: true" in _SRC


def test_prune_skipped_during_load():
    assert "this._loading" in _SRC
    assert "_loading = true" in _SRC


def test_spacer_has_class_name():
    assert "chat-history-spacer" in _SRC


def test_spacer_uses_height_delta():
    assert "delta" in _SRC
    assert "height:" in _SRC


def test_spacer_excluded_from_live_count():
    assert "chat-history-spacer" in _SRC
    assert "this._sentinel" in _SRC


def test_live_child_count_excludes_hist_sep():
    lcc = _SRC[_SRC.index("MessageWindow.prototype._liveChildCount"):]
    lcc = lcc[:lcc.index("MessageWindow.prototype._histChildCount")]
    assert "this._histSep" in lcc


def test_prune_top_excludes_hist_sep():
    pt = _SRC[_SRC.index("MessageWindow.prototype._pruneTop"):]
    pt = pt[:pt.index("MessageWindow.prototype._pruneBottom")]
    assert "this._histSep" in pt


# ---------------------------------------------------------------------------
# sessions.js integration
# ---------------------------------------------------------------------------

def test_sessions_calls_reset_before_clear():
    reset_idx   = _SESS.index("window.chatHistory.reset()")
    inner_idx   = _SESS.index("chatHistory.innerHTML = ''")
    assert reset_idx < inner_idx, "reset() must precede innerHTML = ''"


def test_sessions_calls_load():
    assert "window.chatHistory.load(" in _SESS


def test_sessions_has_direct_render_fallback():
    assert "Fallback: direct render" in _SESS or "window.chatModule.addMessage" in _SESS


def test_sessions_prepares_message_array():
    assert "_preparedMsgs" in _SESS


# ---------------------------------------------------------------------------
# chat.js — resumeStream thinking-token fix
# ---------------------------------------------------------------------------
# The server emits {delta: "...", thinking: true} for reasoning-model tokens.
# resumeStream previously had no _thinkOpen state machine, so thinking tokens
# rendered as visible plain text in the crash-recovery replay bubble.
# These checks lock in the state machine added alongside the virtualization work
# (the thinking-token bug only manifests on the crash-recovery path that this
# PR makes more reliable).

_CHAT = (_REPO / "static/js/chat.js").read_text(encoding="utf-8")


def _resume_stream_body() -> str:
    """Return the source text of the resumeStream function."""
    start = _CHAT.index("export async function resumeStream(")
    # End at the next top-level export function or end of file
    next_export = _CHAT.find("\nexport ", start + 1)
    return _CHAT[start:] if next_export < 0 else _CHAT[start:next_export]


def test_resume_stream_has_think_open_flag():
    # State flag mirrors the main stream handler's _thinkOpen variable.
    assert "let _resumeThinkOpen = false" in _resume_stream_body()


def test_resume_stream_injects_open_think_tag():
    # When json.thinking is true and _resumeThinkOpen is false, prepend <think>
    # so addMessage renders it as a collapsible section instead of plain text.
    body = _resume_stream_body()
    assert "'<think>' + _rdelta" in body or '"<think>" + _rdelta' in body


def test_resume_stream_injects_close_think_tag():
    # When the thinking stream ends (json.thinking is falsy after it was true),
    # prepend </think> to close the block.
    body = _resume_stream_body()
    assert "'</think>' + _rdelta" in body or '"</think>" + _rdelta' in body


def test_resume_stream_closes_unclosed_think_block_after_loop():
    # If the SSE stream ends mid-thinking-block (crash happened inside a
    # reasoning sequence), the dangling <think> is closed before finalization.
    body = _resume_stream_body()
    # Look for the close-if-still-open guard that runs after the for loop
    assert "_resumeThinkOpen" in body
    assert "roundText += '</think>'" in body or 'roundText += "</think>"' in body


def test_resume_stream_strips_think_tags_from_display():
    # renderDelta() strips <think>…</think> blocks from the intermediate display
    # bubble (the "replaying…" indicator) so they don't leak as visible text
    # while the replay is in progress. Two replacements: one for closed blocks
    # (non-greedy) and one for a trailing unclosed block (greedy).
    body = _resume_stream_body()
    assert "dt.replace(/<think" in body
    assert body.count("dt.replace(/<think") == 2
