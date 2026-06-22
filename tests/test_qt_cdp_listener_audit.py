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


def test_console_message_spawns_thread():
    block = _js_console_block()
    assert "_threading.Thread(" in block


def test_console_message_thread_targets_audit():
    block = _js_console_block()
    assert "target=_cdp_audit_listeners," in block


def test_console_message_thread_is_daemon():
    block = _js_console_block()
    assert "daemon=True," in block


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
