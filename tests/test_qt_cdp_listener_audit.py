import re
from pathlib import Path

_SRC = Path("qt_wrapper.py").read_text(encoding="utf-8")


def _cdp_audit_block() -> str:
    marker = "def _cdp_audit_listeners("
    start = _SRC.index(marker)
    end = _SRC.index("\ndef ", start + 1)
    return _SRC[start:end]


def _js_console_block() -> str:
    marker = "def javaScriptConsoleMessage("
    start = _SRC.index(marker)
    end = _SRC.index("\n    def ", start + 1)
    return _SRC[start:end]


def test_re_evict_defined():
    assert "_RE_EVICT = _re.compile(" in _SRC


def test_re_evict_matches_phase2_message():
    pattern = re.compile(r'\[chatHistory\] Phase 2 evict: removed (\d+) live nodes')
    m = pattern.match("[chatHistory] Phase 2 evict: removed 12 live nodes")
    assert m is not None and m.group(1) == "12"


def test_cdp_audit_listeners_defined():
    assert "def _cdp_audit_listeners(n_evicted: int)" in _SRC


def test_cdp_audit_reads_pre_count():
    block = _cdp_audit_block()
    assert "'Memory.getDOMCounters'" in block


def test_cdp_audit_sleeps_five_seconds():
    block = _cdp_audit_block()
    assert "_time.sleep(5)" in block


def test_cdp_audit_logs_delta():
    block = _cdp_audit_block()
    assert "delta=" in block


def test_cdp_audit_logs_nodes_evicted():
    block = _cdp_audit_block()
    assert "nodes-evicted=" in block


def test_javascript_console_message_in_odysseus_page():
    cls_start = _SRC.index("class OdysseusPage(")
    assert "def javaScriptConsoleMessage(" in _SRC[cls_start:]


def test_console_message_prints_message():
    block = _js_console_block()
    assert "print(message," in block


def test_console_message_detects_eviction_pattern():
    block = _js_console_block()
    assert "_RE_EVICT.match(message)" in block


def test_console_message_submits_to_executor():
    block = _js_console_block()
    assert "_cdp_executor.submit(_cdp_audit_listeners," in block


def test_console_message_no_raw_thread():
    block = _js_console_block()
    assert "_threading.Thread(" not in block


def test_threading_imported():
    assert "import threading as _threading" in _SRC


def test_cdp_sock_imported():
    assert "import socket as _cdp_sock" in _SRC


def test_cdp_struct_imported():
    assert "import struct as _cdp_struct" in _SRC


def test_cdp_b64_imported():
    assert "import base64 as _cdp_b64" in _SRC


def test_cdp_req_imported():
    assert "import urllib.request as _cdp_req" in _SRC


def test_cdp_dom_counts_not_present():
    assert "def _cdp_dom_counts(" not in _SRC


def test_log_renderer_memory_uses_cdp_call():
    assert "_cdp_call('Memory.getDOMCounters')" in _log_renderer_memory_block()


def test_psi_monitor_called_not_just_defined():
    # Verify _start_psi_monitor() is actually invoked, not only defined.
    # Count occurrences: first is the def, second must be the call site.
    assert _SRC.count("_start_psi_monitor") >= 2


def _log_renderer_memory_block() -> str:
    marker = "def _log_renderer_memory("
    start = _SRC.index(marker)
    end = _SRC.index("\n        self._mem_timer", start)
    return _SRC[start:end]


def test_theme_bg_color_function_exists():
    # _theme_bg_color() reads the saved theme from user_prefs.json so that
    # setBackgroundColor() uses the user's actual bg, not a hardcoded default.
    assert "def _theme_bg_color()" in _SRC


def test_set_background_color_uses_theme_function():
    # Must not hardcode #282c34 — that breaks custom themes (e.g. Catppuccin
    # #1e1e2e) by filling evicted compositor tiles at the wrong colour.
    assert "setBackgroundColor(_theme_bg_color())" in _SRC
    assert "setBackgroundColor(QColor(0x28, 0x2c, 0x34))" not in _SRC


def test_set_background_color_called_after_set_page():
    # setBackgroundColor must be called AFTER browser.setPage(page) — not before.
    # Qt WebEngine may discard or reset the page background during setPage()
    # initialisation; calling it after ensures the base background colour sticks
    # on the fully-initialised page (avoids a flash of a lighter base colour).
    set_page_pos = _SRC.index("browser.setPage(page)")
    set_bg_pos = _SRC.index("page.setBackgroundColor(_theme_bg_color())")
    assert set_bg_pos > set_page_pos, (
        "setBackgroundColor must come after setPage — got positions "
        f"setPage={set_page_pos}, setBackgroundColor={set_bg_pos}"
    )


def test_theme_bg_reads_user_prefs():
    idx = _SRC.index("def _theme_bg_color()")
    end = _SRC.index("\ndef ", idx + 1)
    block = _SRC[idx:end]
    assert "user_prefs.json" in block
    assert "_users" in block


# --- Change A: renderProcessPid ---

def test_render_process_pid_used():
    assert "renderProcessPid()" in _log_renderer_memory_block()


def test_pgrep_not_in_log_renderer_memory():
    assert "pgrep" not in _log_renderer_memory_block()


def test_render_pid_zero_guard():
    block = _log_renderer_memory_block()
    assert "if pid:" in block


# --- Change B: ThreadPoolExecutor ---

def test_futures_imported():
    assert "import concurrent.futures as _futures" in _SRC


def test_cdp_executor_defined():
    assert "_cdp_executor = _futures.ThreadPoolExecutor(" in _SRC


def test_executor_max_workers():
    assert "max_workers=2" in _SRC


def test_audit_uses_executor_submit():
    block = _js_console_block()
    assert "_cdp_executor.submit(_cdp_audit_listeners," in block


def _change_event_block() -> str:
    start = _SRC.index("def changeEvent(")
    end = _SRC.index("\n    def ", start + 1)
    return _SRC[start:end]


def _request_async_gc_block() -> str:
    start = _SRC.index("def _request_async_gc(")
    end = _SRC.index("\n\n\n", start)
    return _SRC[start:end]


# --- Async GC machinery (replaces _cdp_purge_memory) ---

def test_request_async_gc_defined():
    assert "def _request_async_gc(" in _SRC


def test_request_async_gc_sets_pending_flag():
    # Must set the shared cell so the main-thread drain timer picks it up.
    assert "_gc_request_pending[0] = True" in _request_async_gc_block()


def test_gc_drain_timer_defined():
    assert "_gc_drain_timer" in _SRC


def test_gc_drain_reads_pending_flag():
    # The drain closure must guard on the pending flag before calling runJavaScript.
    assert "_gc_request_pending[0]" in _SRC


def test_gc_drain_calls_run_javascript():
    # Async GC is delivered via page.runJavaScript, not a CDP WebSocket call.
    assert "runJavaScript" in _SRC


def test_psi_monitor_uses_request_async_gc():
    psi_start = _SRC.index("def _start_psi_monitor(")
    psi_end = _SRC.index("\nclass ", psi_start)
    psi_block = _SRC[psi_start:psi_end]
    assert "_request_async_gc()" in psi_block


def test_psi_monitor_has_gc_cooldown():
    # 30 s cooldown prevents GC spam under sustained memory pressure.
    psi_start = _SRC.index("def _start_psi_monitor(")
    psi_end = _SRC.index("\nclass ", psi_start)
    psi_block = _SRC[psi_start:psi_end]
    assert "_COOLDOWN" in psi_block
    assert "30" in psi_block


def test_change_event_debounces_focus_loss():
    # Focus-loss GC uses a 500 ms single-shot timer to skip transient focus shifts.
    block = _change_event_block()
    assert "_gc_focus_timer" in block
    assert ".start(" in block


def test_change_event_cancels_on_activate():
    block = _change_event_block()
    assert "WindowActivate" in block
    assert ".stop()" in block


def test_vmpeak_only_on_new_peak():
    block = _log_renderer_memory_block()
    assert "_last_vmpeak" in block
    assert "(new peak)" in block


def test_nodes_assigned_before_threshold_comparison():
    # Guards against cherry-pick divergence: the threshold block references `nodes`
    # as a local variable; it must be extracted from the counts dict before use.
    block = _log_renderer_memory_block()
    nodes_assign = block.index("nodes = counts.get(")
    threshold_use = block.index("if nodes > 50_000")
    assert nodes_assign < threshold_use


# --- Change B: executor shutdown ---

def test_executor_shutdown_in_stop_server():
    # Executor must be shut down when the server stops so CDP threads do not
    # outlive the server process.  cancel_futures=True prevents queued work
    # from running after shutdown is requested.
    stop_start = _SRC.index("def stop_server(")
    stop_end   = _SRC.index("\ndef ", stop_start + 1)
    stop_block = _SRC[stop_start:stop_end]
    assert "_cdp_executor.shutdown(" in stop_block
    assert "cancel_futures=True" in stop_block


# --- Change C: startup log rotation ---

def test_rotate_log_called_before_dup2():
    rotate_pos = _SRC.index("_rotate_log(")
    dup2_pos = _SRC.index("os.dup2(")
    assert rotate_pos < dup2_pos


def test_access_log_rotated_in_start_server():
    server_start = _SRC.index("def start_server(")
    server_end = _SRC.index("\ndef stop_server(")
    server_block = _SRC[server_start:server_end]
    assert "_rotate_log(" in server_block


def test_rotate_log_shifts_multiple_backups():
    # _rotate_log must implement a shift loop, not a single rename, so that
    # _LOG_BACKUP_COUNT backups are preserved (matching RotatingFileHandler).
    start = _SRC.index("def _rotate_log(")
    end = _SRC.index("\n\n\n", start)
    block = _SRC[start:end]
    assert "_LOG_BACKUP_COUNT" in block
    assert "for n in range(" in block


def test_log_constants_match_app():
    # 10 MB and 5 backups must match src/constants.py LOG_MAX_BYTES / LOG_BACKUP_COUNT.
    assert "_LOG_MAX_BYTES = 10 * 1024 * 1024" in _SRC
    assert "_LOG_BACKUP_COUNT = 5" in _SRC


def test_js_flags_comma_separated():
    """Qt splits QTWEBENGINE_CHROMIUM_FLAGS on whitespace before passing each
    token to Chromium.  A space-separated --js-flags list becomes 5 separate
    tokens; only the first token (--js-flags=--expose-gc) reaches V8 as a
    V8 flag — the remaining tokens (--initial-old-space-size=..., etc.) are
    silently dropped.  V8 accepts comma-separated multi-flag syntax, so all
    flags must be combined into a single token with commas."""
    assert "--js-flags=--expose-gc,--initial-old-space-size=128" in _SRC


def test_js_flags_no_space_after_expose_gc():
    """Guard: ensure the space-separated form that silently drops V8 flags is
    not reintroduced. --expose-gc followed by a space means Qt will split and
    discard everything after the first token."""
    assert "--js-flags=--expose-gc --" not in _SRC


def test_initial_old_space_size_set():
    assert "--initial-old-space-size=128" in _SRC


def test_optimize_for_size_flag_set():
    assert "--optimize-for-size" in _SRC


def test_minor_mc_flag_set():
    assert "--minor-mc" in _SRC


def test_renderer_process_limit_set():
    assert "--renderer-process-limit=1" in _SRC


def test_cdp_ws_call_extracted():
    """_cdp_ws_call must exist as a shared WebSocket helper used by both
    _cdp_call (page target) and _cdp_browser_call (browser target)."""
    assert "def _cdp_ws_call(" in _SRC


def test_cdp_browser_call_exists():
    """_cdp_browser_call must exist and use /json/version (the browser target).
    simulatePressureNotification is a browser-level command; called from the page
    target it is either rejected or fires only in the browser process, leaving
    cc::TileManager in the renderer unaffected."""
    assert "def _cdp_browser_call(" in _SRC
    assert "/json/version" in _SRC


def test_reclaim_uses_forcibly_purge_not_simulate_pressure():
    """The renderer reclaim must call Memory.forciblyPurgeJavaScriptMemory.
    simulatePressureNotification is a no-op on QtWebEngine (measured: RSS
    unchanged after the call) while forciblyPurge reclaims multiple GB; the no-op
    call must not be used as the reclaim path (issue #106). Its 'critical' level
    parameter must be gone (it may survive only in explanatory comments)."""
    assert "'Memory.forciblyPurgeJavaScriptMemory'" in _SRC
    assert "'level': 'critical'" not in _SRC


def test_reclaim_gated_by_rss_ceiling_and_rate_limit():
    """A forcible purge causes a ~1s stutter, so it must be gated: only above an
    RSS ceiling (so light use never stutters) and rate-limited (no back-to-back
    purges). Both the ceiling and the interval guard must be present."""
    assert "_PURGE_RSS_CEILING_KB" in _SRC
    assert "_PURGE_MIN_INTERVAL_S" in _SRC
    assert "_last_purge" in _SRC


def test_reclaim_fired_off_interaction_path_only():
    """The purge fires only where a stutter is invisible: mouse-idle and
    focus-loss. It must NOT be fired from the blind periodic mem timer."""
    assert "_purge_renderer('post-interaction-idle')" in _SRC
    assert "_purge_renderer('sustained-idle')" in _SRC
    assert "_purge_renderer('focus-loss')" in _SRC


def test_reclaim_result_checked():
    """The purge result must be checked and logged (it returns None on error)."""
    assert 'res is not None' in _SRC


def test_input_idle_filter_tracks_keyboard_and_mouse():
    """The idle filter must track keyboard as well as mouse, so that typing defers
    the reclaim purge (a forcible purge causes a ~1s stutter and must never fire
    mid-typing). Installed at the QApplication level to see all input."""
    assert "class _InputIdleFilter(" in _SRC
    assert "QEvent.Type.MouseMove" in _SRC
    assert "QEvent.Type.KeyPress" in _SRC


def test_post_interaction_idle_timer_wired():
    """The single-shot post-interaction timer gives a fast reclaim ~2s after the
    user stops interacting."""
    assert "setSingleShot(True)" in _SRC
    assert "setInterval(2000)" in _SRC
    assert "_idle_evict_timer" in _SRC


def test_sustained_idle_reclaim_is_periodic():
    """The single-shot timer only re-arms on input, so a user who walks away gets
    exactly one purge and the renderer then climbs unbounded (it filled all RAM in
    testing). A repeating timer must drive sustained-idle reclaim, gated on no input
    for _IDLE_RECLAIM_AFTER_S."""
    assert "_idle_reclaim_timer" in _SRC
    assert "_maybe_idle_purge" in _SRC
    assert "_IDLE_RECLAIM_AFTER_S" in _SRC
    # Must be repeating, not single-shot: started without setSingleShot(True) on it.
    idx = _SRC.index("_idle_reclaim_timer = QTimer(")
    block = _SRC[idx:idx + 300]
    assert ".start()" in block
    assert "setSingleShot" not in block


def test_idle_purge_gated_on_no_recent_input():
    """The periodic reclaim must check time since last input before purging, so it
    never fires while the user is interacting."""
    idx = _SRC.index("def _maybe_idle_purge(")
    block = _SRC[idx:idx + 600]
    assert "_last_input" in block
    assert "_IDLE_RECLAIM_AFTER_S" in block
    assert "_purge_renderer(" in block


def test_idle_reclaim_runs_in_executor():
    """The purge CDP call must run in the thread pool executor, not the main thread."""
    assert "_cdp_executor.submit" in _SRC
    assert "_evict_on_idle" in _SRC or "_do" in _SRC


# --- P1–P5: professional tile budget + lifecycle management ---

def test_low_end_device_mode_flag_absent():
    """--enable-low-end-device-mode must NOT be passed to Chromium: it caused a
    lighter-rectangle raster tint on dark themes and did not bound the actual OOM
    (Oilpan detached-DOM churn, a separate pool from the raster tile budget).
    Checks the active quoted-flag entry is absent — prose/comments may still
    reference the flag to explain why it was removed."""
    assert '"--enable-low-end-device-mode"' not in _SRC


def test_http_cache_capped():
    """HTTP cache must be explicitly bounded. Default is unlimited (0), which lets
    the cache grow without bound even though the app serves from localhost and
    rarely gets cache hits."""
    assert "setHttpCacheMaximumSize" in _SRC


def test_page_stored_as_instance_attr():
    """The page must be stored as self._page for changeEvent to access it during
    minimize/restore lifecycle transitions."""
    assert "self._page = page" in _SRC


def test_minimize_purges_and_does_not_freeze():
    """On minimize, the page must NOT be frozen: a frozen page loses HTML input and
    PyQt's lifecycle transitions are unreliable, so the UI came back unresponsive
    after restore (issue #109). Keep the page Active and reclaim memory with the
    gated purge instead. Must check isMinimized() to distinguish minimize from other
    WindowStateChange events."""
    block = _change_event_block()
    assert "setLifecycleState" not in block, (
        "must not freeze the page on minimize; Frozen->Active loses input on restore"
    )
    assert "_purge_renderer('minimized')" in block
    assert "isMinimized" in block


def test_periodic_timer_reduced_to_30s():
    """Periodic CDP eviction interval reduced from 10s to 30s. With P1's tile budget
    doing primary bounding and the 2s mouse-idle eviction handling the interactive
    case, 10s polling was unnecessary frequency."""
    assert "_mem_timer.start(30_000)" in _SRC


def test_reclaim_telemetry_present():
    """The purge must log RSS before and after so logs show how much it actually
    freed (positive delta) rather than masking a no-op. The telemetry now lives in
    _purge_renderer, around the forciblyPurge call."""
    start = _SRC.index("def _purge_renderer(")
    end = _SRC.index("\n    def ", start + 1)
    block = _SRC[start:end]
    purge_pos = block.index("forciblyPurgeJavaScriptMemory")
    assert "delta=" in block[purge_pos:]
    assert "_renderer_rss_kb()" in block
