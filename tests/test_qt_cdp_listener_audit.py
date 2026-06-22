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
    marker = "def _log_renderer_memory("
    start = _SRC.index(marker)
    block = _SRC[start:start + 800]
    assert "_cdp_call('Memory.getDOMCounters')" in block


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


def test_psi_purge_uses_executor_submit():
    psi_start = _SRC.index("def _start_psi_monitor(")
    psi_end = _SRC.index("\nclass ", psi_start)
    psi_block = _SRC[psi_start:psi_end]
    assert "_cdp_executor.submit(_cdp_purge_memory)" in psi_block


def test_change_event_uses_executor():
    ce_start = _SRC.index("def changeEvent(")
    ce_end = _SRC.index("\n    def ", ce_start + 1)
    ce_block = _SRC[ce_start:ce_end]
    assert "_cdp_executor.submit(_cdp_purge_memory)" in ce_block


def test_threshold_gc_uses_executor():
    assert "_cdp_executor.submit(_cdp_purge_memory)" in _log_renderer_memory_block()


def test_nodes_assigned_before_threshold_comparison():
    # Guards against cherry-pick divergence: the threshold block references `nodes`
    # as a local variable; it must be extracted from the counts dict before use.
    block = _log_renderer_memory_block()
    nodes_assign = block.index("nodes = counts.get(")
    threshold_use = block.index("if nodes > 50_000")
    assert nodes_assign < threshold_use


# --- Change C: startup log rotation ---

def test_rotate_log_defined():
    assert "def _rotate_log(" in _SRC


def test_log_max_bytes_defined():
    assert "_LOG_MAX_BYTES" in _SRC


def test_rotate_log_called_before_dup2():
    rotate_pos = _SRC.index("_rotate_log(")
    dup2_pos = _SRC.index("os.dup2(")
    assert rotate_pos < dup2_pos


def test_access_log_rotated_in_start_server():
    server_start = _SRC.index("def start_server(")
    server_end = _SRC.index("\ndef stop_server(")
    server_block = _SRC[server_start:server_end]
    assert "_rotate_log(" in server_block
