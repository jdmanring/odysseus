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


def test_prototype_teardown_node():
    assert "MessageWindow.prototype._teardownNode" in _SRC


def test_no_dead_prune_bottom():
    # _pruneBottom lost its last call site when the Phase-3 bottom prune moved
    # inline into _loadOlder (with spacer/estimator integration the standalone
    # version lacked). Dead code must not ship upstream — and its presence once
    # hid a real defect: the inline path forgot the teardown _pruneBottom had.
    assert "_pruneBottom" not in _SRC


def test_prototype_total_child_count():
    assert "MessageWindow.prototype._totalChildCount" in _SRC


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
    # IO fires on any visibility change including the one the Phase-3 bottom prune causes
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
    pt = pt[:pt.index("window.chatHistory = new MessageWindow")]
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


def test_load_older_phase3_tracks_end_idx_via_ch_idx():
    # The inline Phase-3 bottom prune sets _endIdx = _pruneLowest (data-attribute
    # based) rather than decrementing per DOM node, so multi-child messages track
    # correctly.
    lo = _SRC[_SRC.index("MessageWindow.prototype._loadOlder"):]
    lo = lo[:lo.index("MessageWindow.prototype._isAtVeryBottom")]
    assert "this._endIdx = _pruneLowest" in lo
    assert "chIdx" in lo


def test_load_older_phase3_teardown_before_remove():
    # The inline bottom prune removes nodes that the very same function just
    # registered with the hljs-defer observer (deferHighlightAll on each batch).
    # Skipping teardown here retains every cycled code block in the shared
    # observer — the exact leak class this file exists to close. Both the main
    # loop and the boundary peek must tear down before .remove().
    lo = _SRC[_SRC.index("MessageWindow.prototype._loadOlder"):]
    lo = lo[:lo.index("MessageWindow.prototype._isAtVeryBottom")]
    main_td = lo.index("this._teardownNode(_pRef)")
    assert main_td < lo.index("_pRef.remove()", main_td), (
        "_loadOlder Phase-3 main loop must call _teardownNode before _pRef.remove()"
    )
    peek_td = lo.index("this._teardownNode(_pPeek)")
    assert peek_td < lo.index("_pPeek.remove()", peek_td), (
        "_loadOlder Phase-3 boundary peek must call _teardownNode before _pPeek.remove()"
    )


def test_load_newer_phase3_teardown_before_remove():
    # Same contract for the inline top prune in _loadNewer (main + boundary peek).
    ln = _load_newer_body()
    main_td = ln.index("this._teardownNode(cur)")
    assert main_td < ln.index("cur.remove()", main_td), (
        "_loadNewer Phase-3 main loop must call _teardownNode before cur.remove()"
    )
    peek_td = ln.index("this._teardownNode(peek)")
    assert peek_td < ln.index("peek.remove()", peek_td), (
        "_loadNewer Phase-3 boundary peek must call _teardownNode before peek.remove()"
    )


def _teardown_node_body() -> str:
    start = _SRC.index("MessageWindow.prototype._teardownNode")
    end   = _SRC.index("MessageWindow.prototype._pruneTop", start)
    return _SRC[start:end]


def test_teardown_node_releases_full_reference_set():
    # The helper is the single definition of "what a removed node retains":
    # timer handles, the StreamRenderer reference, and the hljs-defer observer
    # registration — on the node itself AND its descendants.
    body = _teardown_node_body()
    assert "_waveInterval" in body
    assert "_elapsedTicker" in body
    assert "_streamRenderer" in body
    assert "querySelectorAll('*')" in body
    assert "window.hljsDeferForgetNode" in body


def test_every_removal_path_uses_teardown_node():
    # Seven removal sites: _pruneTop (main + peek), _evictLive, _loadOlder
    # Phase-3 (main + peek), _loadNewer Phase-3 (main + peek). The helper is
    # called at all of them; no removal path may hand-roll its own subset.
    assert _SRC.count("this._teardownNode(") >= 7


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
    # Prune passes must record the EXACT measured scrollHeight delta (not an
    # estimate) so the estimator-spacer recompute reproduces the removed height
    # to the pixel and the saved scrollTop restore does not jump.
    assert "before - this._c.scrollHeight" in _SRC
    assert "_recordPruneHeights(_msgPx, totalDelta)" in _SRC
    assert ".style.height = h + 'px'" in _SRC


def test_spacer_excluded_from_live_count():
    assert "chat-history-spacer" in _SRC
    assert "this._sentinel" in _SRC


def test_total_child_count_excludes_hist_sep():
    lcc = _SRC[_SRC.index("MessageWindow.prototype._totalChildCount"):]
    lcc = lcc[:lcc.index("MessageWindow.prototype._histChildCount")]
    assert "this._histSep" in lcc


def test_total_child_count_excludes_evict_notice():
    # The in-place eviction notice must not count toward the pruning threshold,
    # otherwise it inflates the total and causes spurious eviction on every tick.
    lcc = _SRC[_SRC.index("MessageWindow.prototype._totalChildCount"):]
    lcc = lcc[:lcc.index("MessageWindow.prototype._histChildCount")]
    assert "chat-live-evict-notice" in lcc


def test_prune_top_excludes_hist_sep():
    pt = _SRC[_SRC.index("MessageWindow.prototype._pruneTop"):]
    pt = pt[:pt.index("window.chatHistory = new MessageWindow")]
    assert "this._histSep" in pt


# ---------------------------------------------------------------------------
# Phase 2 — live-message eviction (_evictLive, fix/dom-oom-phase2-guard)
# ---------------------------------------------------------------------------
# When history is exhausted (hist === 0) and live messages overflow PRUNE_AT,
# _maybePrune() must route to _evictLive() instead of returning early.
# Previously the hard-stop "if (hist === 0) return;" caused live messages
# to accumulate without bound for the rest of the session.

def _maybe_prune_body() -> str:
    start = _SRC.index("MessageWindow.prototype._maybePrune")
    end   = _SRC.index("MessageWindow.prototype.", start + 1)
    return _SRC[start:end]


def _evict_live_body() -> str:
    start = _SRC.index("MessageWindow.prototype._evictLive")
    end   = _SRC.index("MessageWindow.prototype.", start + 1)
    return _SRC[start:end]


def test_prototype_evict_live():
    assert "MessageWindow.prototype._evictLive" in _SRC


def test_prototype_update_evict_notice():
    assert "MessageWindow.prototype._updateEvictNotice" in _SRC


def test_evicted_live_count_initialized():
    # _evictedLiveCount must be set to 0 in the constructor so it survives a
    # session with no evictions and resets cleanly on session switch.
    ctor_start = _SRC.index("function MessageWindow(")
    ctor_end   = _SRC.index("MessageWindow.prototype", ctor_start)
    ctor = _SRC[ctor_start:ctor_end]
    assert "_evictedLiveCount" in ctor


def test_evicted_live_count_reset():
    reset = _SRC[_SRC.index("MessageWindow.prototype.reset"):]
    reset = reset[:reset.index("MessageWindow.prototype.", len("MessageWindow.prototype.reset"))]
    assert "_evictedLiveCount" in reset


def test_maybe_prune_no_hard_stop_on_hist_zero():
    # The old "if (hist === 0) return;" permanently disabled Phase 2 once
    # all historical nodes were pruned. Verify it is gone.
    body = _maybe_prune_body()
    assert "if (hist === 0) return;" not in body


def test_maybe_prune_routes_to_evict_live():
    # When hist > 0 prune historical nodes; when hist === 0 evict live nodes.
    body = _maybe_prune_body()
    assert "_evictLive" in body
    assert "_pruneTop" in body


def test_evict_live_clears_wave_interval():
    # Timer teardown lives in the shared _teardownNode helper; _evictLive must
    # invoke it for every removed node.
    assert "_teardownNode" in _evict_live_body()
    body = _teardown_node_body()
    assert "_waveInterval" in body
    assert "clearInterval" in body


def test_evict_live_clears_elapsed_ticker():
    assert "_elapsedTicker" in _teardown_node_body()


def test_evict_live_clears_stream_renderer():
    assert "_streamRenderer" in _teardown_node_body()


def test_evict_live_calls_update_notice():
    body = _evict_live_body()
    assert "_updateEvictNotice" in body


def test_evict_notice_has_reload_hint():
    # Notice text must tell the user how to see evicted messages.
    notice = _SRC[_SRC.index("MessageWindow.prototype._updateEvictNotice"):]
    notice = notice[:notice.index("MessageWindow.prototype.", len("MessageWindow.prototype._updateEvictNotice"))]
    assert "reload" in notice.lower()


def test_evict_notice_class_name():
    assert "chat-live-evict-notice" in _SRC


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


# ---------------------------------------------------------------------------
# _evictLive — structural and scroll-compensation contracts
# ---------------------------------------------------------------------------
# These tests verify invariants that the existing teardown tests do not cover:
# scroll position preservation, descendant-level cleanup, and control-element
# skip logic.  All are correctness-critical: a violation causes either a visible
# scroll jump or a memory leak for interval/renderer objects on child nodes.

def _update_evict_notice_body() -> str:
    start = _SRC.index("MessageWindow.prototype._updateEvictNotice")
    end   = _SRC.index("MessageWindow.prototype._totalChildCount")
    return _SRC[start:end]


def test_evict_live_captures_scroll_top_before_removal():
    # scrollTop must be saved BEFORE the removal loop.  The browser clamps
    # scrollTop when scrollHeight shrinks; saving after removal captures the
    # already-clamped (wrong) value and the compensation is a no-op.
    body = _evict_live_body()
    saved_idx  = body.index("savedScrollTop")
    remove_idx = body.index("el.remove()")
    assert saved_idx < remove_idx, (
        "savedScrollTop must be captured before el.remove() is called"
    )


def test_evict_live_restores_scroll_top_after_removal():
    # After removal the browser clamps scrollTop; the method must reassign it
    # to undo the clamp and keep the user's visual position stable.
    body       = _evict_live_body()
    remove_idx = body.index("el.remove()")
    assign_idx = body.index("this._c.scrollTop =", remove_idx)
    assert assign_idx > remove_idx, (
        "this._c.scrollTop must be reassigned after el.remove()"
    )


def test_evict_live_iterates_descendants():
    # Teardown must recurse into every descendant via querySelectorAll('*').
    # Intervals and streamRenderers are attached to child nodes (e.g. the
    # inner div of a thinking block), not always the top-level round element.
    # The walk lives in the shared _teardownNode helper.
    body = _teardown_node_body()
    assert ("querySelectorAll('*')" in body or 'querySelectorAll("*")' in body), (
        "_teardownNode must walk all descendants with querySelectorAll('*')"
    )


def test_evict_live_teardown_applied_to_descendants():
    # The same _waveInterval / _elapsedTicker / _streamRenderer cleanup that
    # runs on the top-level node must also run on each descendant `d` — the
    # shared _teardownNode helper carries that contract for every removal path.
    body = _teardown_node_body()
    assert "d._waveInterval" in body
    assert "d._elapsedTicker" in body
    assert "d._streamRenderer" in body


def test_evict_live_skips_control_elements():
    # The sentinel, spacer, and the eviction notice itself must never be
    # collected into toRemove — evicting them would corrupt the virtualization
    # state machine.
    body = _evict_live_body()
    assert "chat-history-spacer" in body, (
        "_evictLive must skip .chat-history-spacer nodes"
    )
    assert "chat-live-evict-notice" in body, (
        "_evictLive must skip the eviction notice to avoid evicting it"
    )


# ---------------------------------------------------------------------------
# _updateEvictNotice — correctness contracts
# ---------------------------------------------------------------------------

def test_update_evict_notice_shows_count():
    # Notice text must include the running eviction count so the user knows
    # how many messages are hidden.
    body = _update_evict_notice_body()
    assert "this._evictedLiveCount" in body
    assert "textContent" in body


def test_update_evict_notice_handles_singular_plural():
    # "1 earlier message" (singular) vs "2 earlier messages" (plural).
    # Displaying "1 earlier messages" is grammatically wrong and looks sloppy.
    body = _update_evict_notice_body()
    assert "!== 1" in body or "=== 1" in body, (
        "_updateEvictNotice must branch on count for singular/plural form"
    )


def test_update_evict_notice_reuses_existing_element():
    # On repeated eviction events the method must update the existing notice
    # rather than appending a new one each time.  Creating a new element each
    # call would: (a) inflate DOM and (b) distort _totalChildCount (the notice
    # is excluded from the threshold — multiple notices would be counted).
    body       = _update_evict_notice_body()
    qs_idx     = body.index("querySelector")
    ce_idx     = body.index("createElement")
    assert qs_idx < ce_idx, (
        "_updateEvictNotice must querySelector for an existing notice "
        "before calling createElement"
    )


def test_update_evict_notice_inserts_after_hist_sep():
    # The notice must appear just above the live section (immediately after
    # _histSep) so it is visible when the user is near the top of live messages.
    body = _update_evict_notice_body()
    assert "_histSep" in body
    assert "insertAdjacentElement" in body or "insertBefore" in body


# ---------------------------------------------------------------------------
# IntersectionObserver cleanup — hljsDeferForgetNode calls before removal
# ---------------------------------------------------------------------------
# hljsDefer.js registers a shared IntersectionObserver for every <pre><code>
# element added during load or streaming. If chatHistory.js removes a node
# without calling forgetNode(), the observer retains a reference to each
# contained code block and prevents its GC. The guard is optional (the global
# is only present when chat.js has initialised) so the tests verify that the
# call is made and that it precedes removal in both eviction paths.

def test_prune_top_teardown_before_remove():
    # Observer refs, timers and StreamRenderer refs are released via
    # _teardownNode; both the main loop and the boundary peek must call it
    # before .remove().
    body = _prune_top_body()
    main_td = body.index("this._teardownNode(ch)")
    assert main_td < body.index("ch.remove()", main_td), (
        "_pruneTop must call _teardownNode before ch.remove()"
    )
    peek_td = body.index("this._teardownNode(peek)")
    assert peek_td < body.index("peek.remove()", peek_td), (
        "_pruneTop boundary-cleanup pass must call _teardownNode before peek.remove()"
    )


def test_evict_live_teardown_before_remove():
    body = _evict_live_body()
    td_pos = body.index("this._teardownNode(el)")
    remove_pos = body.index("el.remove()", td_pos)
    assert td_pos < remove_pos, (
        "_evictLive must call _teardownNode before el.remove()"
    )


def test_forget_node_calls_guarded_by_window_check():
    # chatHistory.js is loaded before chat.js sets the global; the guard
    # prevents a ReferenceError during the window between page load and init.
    body = _teardown_node_body()
    assert "if (window.hljsDeferForgetNode) window.hljsDeferForgetNode(" in body, (
        "hljsDeferForgetNode must be accessed via window with a presence guard"
    )


# ---------------------------------------------------------------------------
# Observability — console.debug logging
# ---------------------------------------------------------------------------
# Each key operation logs a '[chatHistory]' prefixed message so operators can
# diagnose OOM behaviour in production by filtering DevTools console output
# without modifying code.

def _load_body() -> str:
    start = _SRC.index("MessageWindow.prototype.load")
    end   = _SRC.index("MessageWindow.prototype.reset")
    return _SRC[start:end]


def _prune_top_body() -> str:
    start = _SRC.index("MessageWindow.prototype._pruneTop")
    end   = _SRC.index("window.chatHistory = new MessageWindow", start)
    return _SRC[start:end]


def _load_older_body() -> str:
    start = _SRC.index("MessageWindow.prototype._loadOlder")
    end   = _SRC.index("MessageWindow.prototype._isAtVeryBottom")
    return _SRC[start:end]


def _load_newer_body() -> str:
    start = _SRC.index("MessageWindow.prototype._loadNewer")
    end   = _SRC.index("MessageWindow.prototype._initMutObs")
    return _SRC[start:end]


def test_load_logs_console_log():
    # Session load is a significant event — visible by default (console.log).
    assert "console.log" in _load_body(), (
        "load() must use console.log (visible by default) to log session size"
    )


def test_prune_top_logs_console_log():
    # Temporarily promoted to console.log for active OOM debugging.
    assert "console.log" in _prune_top_body(), (
        "_pruneTop must log the prune count and new startIdx"
    )


def test_evict_live_logs_console_log():
    # Live eviction is a significant event (live messages lost from view) — console.log.
    assert "console.log" in _evict_live_body(), (
        "_evictLive must use console.log (visible by default) to log eviction count"
    )


def test_load_older_logs_console_log():
    # Temporarily promoted to console.log for active OOM debugging.
    assert "console.log" in _load_older_body(), (
        "_loadOlder must log the batch range and node count"
    )


def test_load_newer_logs_console_log():
    # Temporarily promoted to console.log for active OOM debugging.
    assert "console.log" in _load_newer_body(), (
        "_loadNewer must log the batch range and node count"
    )


def test_all_logs_use_consistent_prefix():
    # All console.log and console.debug calls must use '[chatHistory]' so they
    # can be filtered as a group in DevTools (Console → Filter → '[chatHistory]').
    # Significant events (session load, eviction, Phase 3 prune) use console.log
    # (visible by default); routine batch loads and Phase 2 prunes use console.debug
    # (opt-in via Verbose) to avoid noise during normal scroll.
    import re
    calls = re.findall(r"console\.(?:log|debug)\(['\"]([^'\"]+)", _SRC)
    assert calls, "Expected at least one console.log/debug call in chatHistory.js"
    bad = [c for c in calls if not c.startswith('[chatHistory]')]
    assert not bad, (
        "These console calls are missing the '[chatHistory]' prefix: " + str(bad)
    )


# ---------------------------------------------------------------------------
# GC micro-improvements: idle yield + teardown gap
# ---------------------------------------------------------------------------

def _evict_live_block() -> str:
    start = _SRC.index("MessageWindow.prototype._evictLive")
    end = _SRC.index("MessageWindow.prototype._updateEvictNotice", start)
    return _SRC[start:end]


def _prune_top_block() -> str:
    start = _SRC.index("MessageWindow.prototype._pruneTop")
    end = _SRC.index("// ---------------------------------------------------------------------------\n  // Singleton", start)
    return _SRC[start:end]


def test_evict_live_yields_to_idle():
    """_evictLive must signal idle after removing nodes so V8/Oilpan can collect them."""
    assert "requestIdleCallback" in _evict_live_block()


def test_prune_top_yields_to_idle():
    """_pruneTop must signal idle after removing nodes."""
    assert "requestIdleCallback" in _prune_top_block()


def test_inline_phase3_prunes_yield_to_idle():
    """Both inline Phase-3 prunes (_loadOlder bottom, _loadNewer top) must
    signal idle after removing nodes, mirroring _pruneTop/_evictLive."""
    lo = _SRC[_SRC.index("MessageWindow.prototype._loadOlder"):]
    lo = lo[:lo.index("MessageWindow.prototype._isAtVeryBottom")]
    assert "requestIdleCallback" in lo
    assert "requestIdleCallback" in _load_newer_body()


def test_prune_top_clears_intervals_before_remove():
    """_pruneTop must release timer handles (via _teardownNode) before .remove()."""
    assert "_teardownNode" in _prune_top_block()
    assert "_waveInterval" in _teardown_node_body()


# ---------------------------------------------------------------------------
# Scroll-down is the inverse of scroll-up, not a drain-to-bottom (#103)
# ---------------------------------------------------------------------------

def _load_newer_body() -> str:
    """The _loadNewer prototype body (up to the next prototype assignment)."""
    start = _SRC.index("MessageWindow.prototype._loadNewer = function ()")
    end = _SRC.index("MessageWindow.prototype.", start + 1)
    return _SRC[start:end]


def test_load_newer_recursion_gated_on_draining_only():
    # A scroll-driven load must process exactly one batch and stop; only the
    # scroll-to-bottom button (_draining) may cascade. The old code recursed on
    # `_draining || _isAtBottom()`, which made any scroll-down near the bottom
    # drain to the end and behave like the scroll-to-bottom button.
    body = _load_newer_body()
    assert "self._draining || self._isAtBottom()" not in body, (
        "scroll-down must not cascade on _isAtBottom() proximity; gate on _draining only"
    )
    # The non-draining path must early-return after one batch. Its only
    # permitted chain is the bottom-spacer catch-up: when the viewport is
    # parked inside the blank honesty spacer (deep thumb-drag), the spacer
    # shrinking generates no scroll events, so the load must self-continue.
    # That is NOT a proximity cascade — the check is against the spacer rect,
    # never _isAtBottom().
    gate = body.index("if (!self._draining) {")
    block = body[gate:body.index("return;\n", gate) + len("return;")]
    assert "_botSpacer" in block, "non-drain chain must be gated on the bottom spacer"
    assert "_isAtBottom" not in block


def test_load_newer_end_snap_is_drain_only():
    # The early `if (!self._draining) return;` precedes the reached-end snap and
    # settle loop, so a scroll that reaches the newest message stops at the
    # user's position instead of yanking to the bottom.
    body = _load_newer_body()
    gate = body.index("if (!self._draining) {")
    end_snap = body.index("scrollHeight - self._c.clientHeight", gate)
    # The settle loop (drain-only re-snap) must come after the gate.
    assert "_settle" in body[gate:], "settle loop must be inside the drain-only path"
    assert gate < end_snap


def test_bottom_sentinel_says_newer_not_earlier():
    # Scroll-down loads newer messages; the bottom sentinel wording must reflect that.
    assert "newer messages, scroll down to load" in _SRC
    assert "earlier messages — scroll down" not in _SRC


def test_sentinel_observer_reads_newest_entry():
    # IO queues one entry per transition between deliveries; under a
    # busy main thread (batch render) the sentinel can leave and re-enter before
    # delivery, so one callback carries [leave, enter]. Reading entries[0] (the
    # oldest) sees the stale leave, returns without disconnecting, and discards
    # the enter — paging dead-ends permanently at the top (captured live: a
    # single delivery with isIntersecting [false, true]). The callback must act
    # on the NEWEST queued entry.
    assert "entries[entries.length - 1].isIntersecting" in _SRC
    assert "entries[0].isIntersecting" not in _SRC


# --- Scrollbar honesty spacer (top estimator) -------------------------------

def test_top_spacer_is_idempotent_recompute():
    # The spacer height must be recomputed from per-message records + estimate
    # each time, never accumulated incrementally: estimated increments compound
    # error over a deep walk (measured ~220k px short in a benchmark arm that
    # accumulated). The recompute loop walks the absolute range with a
    # per-message fallback to the running estimate.
    upd = _SRC[_SRC.index("MessageWindow.prototype._updateTopSpacer"):]
    upd = upd[:upd.index("MessageWindow.prototype._attachSentinel")]
    assert "for (var abs = 0; abs < count; abs++)" in upd
    assert "this._hpx[abs]" in upd
    assert "+=" not in upd.replace("h += ", "")  # only the recompute sum


def test_height_records_use_absolute_db_index():
    # chIdx shifts on every server prepend (the retag bug class); height records
    # must be keyed by absolute DB index, which never shifts.
    assert "this._serverOffset + chIdx" in _SRC


def test_estimator_folds_only_in_compensated_contexts():
    # The estimator average may only change where a scrollTop compensation
    # absorbs the resulting spacer resize (_loadOlder/_loadNewer). Prune paths
    # record into the pending pool; folding there would shift every unmeasured
    # spacer term above the viewport with no compensation -> visible jump.
    prune_top = _SRC[_SRC.index("MessageWindow.prototype._pruneTop"):]
    prune_top = prune_top[:prune_top.index("window.chatHistory = new MessageWindow")]
    assert "_estFold" not in prune_top
    assert "_estPendSum" in _SRC and "_estPendCount" in _SRC
    assert _SRC.count("this._estFold();") == 2  # _loadOlder + _loadNewer only


def test_deep_drag_assist_and_catchup_chain():
    # A thumb drag into the spacer parks the viewport where the sentinel cannot
    # fire; the scroll listener must trigger paging, and the load-completion
    # rAF must re-check (the spacer shrinking above the viewport generates no
    # scroll events, so without the re-check the catch-up dead-ends). The
    # condition must be BLANK IN VIEW (spacer edge crossing the viewport), not
    # a proximity margin: with a margin, every ordinary scroll-up near the
    # sentinel would chain-drain the entire history and every server page.
    assert _SRC.count("_sR.bottom > _cR.top)") == 1
    assert "sRect.bottom > cRect.top)" in _SRC
    assert "_sR.bottom > _cR.top - 300" not in _SRC
    assert "_bR.top < _cR2.bottom)" in _SRC


# ---------------------------------------------------------------------------
# Part-4 audit fixes: drain latch + stale-generation rAF ordering
# ---------------------------------------------------------------------------

def _scroll_to_bottom_body() -> str:
    start = _SRC.index("MessageWindow.prototype.scrollToBottom")
    end   = _SRC.index("MessageWindow.prototype.", start + 1)
    return _SRC[start:end]


def test_scroll_to_bottom_clears_draining_when_nothing_to_drain():
    # scrollToBottom() with everything already rendered has no _loadNewer drain
    # to run, and a completed drain is the only other thing that clears
    # _draining. A latched flag suppresses the bottom honesty spacer and makes
    # the next scroll-up prune's rAF re-enter drain mode, yanking the user back
    # to the bottom.
    body = _scroll_to_bottom_body()
    assert "this._draining = false" in body, (
        "scrollToBottom must clear _draining when _endIdx >= _all.length"
    )


def test_stale_gen_raf_checks_gen_before_touching_state():
    # A stale rAF (session switched between schedule and fire) must return on
    # the generation check BEFORE calling _clearBusy or touching _draining:
    # reset() already cleared both for the new session, and a late _clearBusy
    # would clear an aria-busy the new session's load just set.
    import re
    assert not re.search(
        r"self\._clearBusy\(\);\s*\n\s*if \(self\._gen !==", _SRC
    ), "gen check must precede _clearBusy in load-completion rAFs"
    assert "{ self._draining = false; return; }" not in _SRC, (
        "stale-gen path must not touch _draining (reset() owns it)"
    )


# ---------------------------------------------------------------------------
# Header message counter — messageCount() wiring
# ---------------------------------------------------------------------------
# The header "· N msgs" counter counted top-level DOM nodes, which was correct
# only while the DOM held the whole conversation. Under windowing the DOM holds
# at most the window, so the counter must read the window layer's
# messageCount() (server total + live messages) and fall back to a
# continuation-aware DOM count only when no total is known.

_APP = (_REPO / "static/app.js").read_text(encoding="utf-8")


def test_chathistory_exposes_message_count():
    assert "MessageWindow.prototype.messageCount = function" in _SRC


def test_load_accepts_server_total_and_resets_live_count():
    assert "opts.serverTotal" in _SRC
    load_start = _SRC.index("MessageWindow.prototype.load = function")
    load_body = _SRC[load_start:_SRC.index("MessageWindow.prototype.reset")]
    assert "_serverTotal" in load_body and "_liveMsgs" in load_body


def test_live_counting_skips_continuations_and_stream_holders():
    count_start = _SRC.index("MessageWindow.prototype._countLiveMessages")
    body = _SRC[count_start:count_start + 1200]
    assert "msg-continuation" in body
    assert "streaming" in body
    assert "data-ch-idx" in body


def test_sessions_passes_server_total_to_load():
    assert "serverTotal:" in _SESS
    load_call = _SESS.index("window.chatHistory.load(_preparedMsgs")
    assert "serverTotal" in _SESS[load_call:load_call + 600]


def test_header_counter_prefers_message_count_with_dom_fallback():
    assert "window.chatHistory.messageCount" in _APP
    # The fallback must not count round continuations as messages.
    assert ":scope > .msg:not(.msg-continuation)" in _APP


def test_every_history_wipe_is_preceded_by_reset():
    """The window layer's API contract: reset() before clearing the container.

    A wipe without reset leaves the previous session's window state (and its
    messageCount total) alive behind an empty pane — the header then shows the
    old session's count on the welcome screen / an empty session.
    """
    import re
    wipes = [m.start() for m in re.finditer(
        r"(?:chatHistory|el\('chat-history'\))\.innerHTML = ''", _SESS)]
    assert wipes, "expected chat-history wipes in sessions.js"
    for pos in wipes:
        window = _SESS[max(0, pos - 400):pos]
        assert "window.chatHistory.reset()" in window, (
            f"chat-history wipe at offset {pos} has no preceding "
            "window.chatHistory.reset() within 400 chars"
        )
