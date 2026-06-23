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


def test_tile_eviction_uses_browser_target():
    """
    The tile eviction call must use _cdp_browser_call, not _cdp_call.
    Memory.simulatePressureNotification must be sent to the browser target so the
    browser process broadcasts the pressure notification to all renderer processes
    via IPC, reaching cc::TileManager where the accumulated hover tiles live.
    """
    assert "_cdp_browser_call('Memory.simulatePressureNotification'" in _SRC
    assert "'level': 'moderate'" in _SRC


def test_hover_transition_suppress_script_injected():
    """
    A QWebEngineScript named 'qt-transition-suppress' must be injected at
    DocumentReady. It restricts transition-property to opacity and transform
    via !important, eliminating ~9 raster tile frames per hover event from
    transition: all rules without removing compositor-promoted animations.
    """
    assert "qt-transition-suppress" in _SRC
    assert "transition: none !important" in _SRC
    assert "DocumentReady" in _SRC


def test_paint_skip_script_injected():
    """
    A QWebEngineScript named 'qt-paint-skip' must be injected at DocumentReady.
    It captures each element's non-hover background-color/border-color/box-shadow
    on first mouseleave (Chromium removes :hover before dispatching mouseleave),
    then inserts a CSSStyleSheet rule forcing :hover to those exact values.
    Chromium's paint-invalidation check sees no computed-value change on subsequent
    hovers and skips rasterization — zero tile frames after first hover cycle.
    """
    assert "qt-paint-skip" in _SRC
    assert "mouseleave" in _SRC
    assert "CSSStyleSheet" in _SRC
    assert "adoptedStyleSheets" in _SRC
    assert "data-qths" in _SRC or "qths" in _SRC
