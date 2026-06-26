"""Static guards for host-process RSS telemetry in qt_wrapper.py (issue #112).

The host process (qt_wrapper.py) embeds Chromium's browser process plus the
in-process GPU thread and network/tracing services, making it the largest single
consumer in the stack. The renderer-pid reading in _log_renderer_memory does NOT
cover it. These tests assert the host VmRSS line is emitted on every memory tick,
with a per-sample delta so growth-over-time is visible in the logs.

No browser required — all checks are static assertions on qt_wrapper.py source.
"""
from pathlib import Path

_SRC = Path("qt_wrapper.py").read_text(encoding="utf-8")


def _log_block() -> str:
    start = _SRC.index("def _log_renderer_memory(")
    end = _SRC.index("\n        def ", start + 1)
    return _SRC[start:end]


def test_host_rss_tracking_cell_present():
    # Mutable closure cell holding the previous host RSS sample.
    assert "_last_host_rss: list[int] = [0]" in _SRC


def test_host_rss_read_from_proc_self():
    block = _log_block()
    assert "/proc/self/status" in block


def test_host_rss_line_emitted():
    block = _log_block()
    assert "[MEM] host pid=" in block
    assert "VmRSS" in block


def test_host_rss_reports_delta():
    # The per-sample delta is what makes baseline-vs-climbing visible.
    block = _log_block()
    assert "delta=" in block
    assert "_last_host_rss[0]" in block


def test_host_rss_distinct_from_renderer_pid():
    # Host line uses os.getpid(); the renderer line uses page.renderProcessPid().
    block = _log_block()
    assert "os.getpid()" in block
    assert "renderProcessPid()" in block
