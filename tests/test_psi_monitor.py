"""Unit tests for the PSI detection core (issue #120).

The detection logic lives in qt_psi, a Qt-free module, so these run in any environment
(the GUI PyQt6 stack is a stub in the server venv) — no importorskip, no silent skip.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import qt_psi  # noqa: E402  (Qt-free; imports without PyQt)

import pytest  # noqa: E402


# --- psi_level: harness CalculatePressureLevel boundaries ---

@pytest.mark.parametrize("some, full, expected", [
    (0.0, 0.0, "NONE"),
    (9.9, 0.0, "NONE"),       # just below MODERATE
    (10.0, 0.0, "MODERATE"),  # MODERATE entry (inclusive)
    (39.9, 0.0, "MODERATE"),  # just below CRITICAL
    (40.0, 0.0, "CRITICAL"),  # CRITICAL via some (inclusive)
    (0.0, 4.9, "NONE"),       # full just below full_critical
    (0.0, 5.0, "CRITICAL"),   # CRITICAL via full (inclusive)
    (12.0, 5.0, "CRITICAL"),  # full dominates even when some is only MODERATE
])
def test_psi_level_boundaries(some, full, expected):
    assert qt_psi.psi_level(
        some, full, moderate=10.0, critical=40.0, full_critical=5.0) == expected


# --- psi_should_emit: the three-arm notify discipline ---

def test_emit_on_level_change_up():
    assert qt_psi.psi_should_emit(
        "NONE", "MODERATE", now=100.0, last_emit=100.0, cooldown=10) is True


def test_moderate_sustained_waits_for_cooldown():
    # Sustained MODERATE: no re-emit before cooldown, re-emit at/after it.
    assert qt_psi.psi_should_emit(
        "MODERATE", "MODERATE", now=105.0, last_emit=100.0, cooldown=10) is False
    assert qt_psi.psi_should_emit(
        "MODERATE", "MODERATE", now=111.0, last_emit=100.0, cooldown=10) is True


def test_critical_emits_every_poll():
    # CRITICAL always notifies, even sustained and well within any cooldown.
    assert qt_psi.psi_should_emit(
        "CRITICAL", "CRITICAL", now=101.0, last_emit=100.0, cooldown=10) is True


def test_none_emits_only_on_down_transition():
    # Down-transition out of pressure -> emit once; staying idle -> silent (no flap).
    assert qt_psi.psi_should_emit(
        "MODERATE", "NONE", now=200.0, last_emit=100.0, cooldown=10) is True
    assert qt_psi.psi_should_emit(
        "NONE", "NONE", now=300.0, last_emit=100.0, cooldown=10) is False


# --- /proc/meminfo helpers ---

_MEMINFO = (
    "MemTotal:       16384000 kB\n"
    "MemFree:          512000 kB\n"
    "MemAvailable:     420000 kB\n"
    "SwapTotal:       4096000 kB\n"
    "SwapFree:        3200000 kB\n"
)


def _meminfo_reader(path):
    """Rebind the real parser at a fixture path."""
    def reader(*keys):
        out = {k: None for k in keys}
        try:
            with open(path) as fh:
                for line in fh:
                    field = line.split(":", 1)
                    if field[0] in out:
                        out[field[0]] = int(field[1].split()[0])
        except (OSError, ValueError, IndexError):
            pass
        return out
    return reader


def test_mem_available_and_swap_used(tmp_path, monkeypatch):
    f = tmp_path / "meminfo"
    f.write_text(_MEMINFO)
    monkeypatch.setattr(qt_psi, "read_meminfo_kb", _meminfo_reader(str(f)))
    avail_mb, swap_mb = qt_psi.read_system_mem_mb()
    assert avail_mb == 420000 // 1024
    assert swap_mb == (4096000 - 3200000) // 1024


def test_meminfo_missing_keys_return_none(tmp_path, monkeypatch):
    f = tmp_path / "meminfo"
    f.write_text("MemTotal: 16384000 kB\n")  # no MemAvailable / Swap*
    monkeypatch.setattr(qt_psi, "read_meminfo_kb", _meminfo_reader(str(f)))
    avail_mb, swap_mb = qt_psi.read_system_mem_mb()
    assert avail_mb is None
    assert swap_mb is None


# --- /proc/pressure/memory parse ---

def test_parse_psi_avg10():
    text = ("some avg10=12.34 avg60=5.00 avg300=1.00 total=999\n"
            "full avg10=6.78 avg60=2.00 avg300=0.50 total=500\n")
    some, full = qt_psi.parse_psi_avg10(text)
    assert some == pytest.approx(12.34)
    assert full == pytest.approx(6.78)


def test_parse_psi_avg10_malformed_defaults_zero():
    some, full = qt_psi.parse_psi_avg10("garbage\n")
    assert some == 0.0 and full == 0.0


# --- dispatch_psi_action: the drain's action dispatch (incl. the CRITICAL path) ---

def _record_calls():
    calls = {"async_gc": 0, "critical": 0}

    def on_async_gc():
        calls["async_gc"] += 1

    def on_critical():
        calls["critical"] += 1
        return on_critical.status
    on_critical.status = "submitted"
    return calls, on_async_gc, on_critical


def test_dispatch_async_gc_runs_gc_only():
    calls, on_async_gc, on_critical = _record_calls()
    label = qt_psi.dispatch_psi_action(
        "async_gc", on_async_gc=on_async_gc, on_critical=on_critical)
    assert label == "async_gc"
    assert calls == {"async_gc": 1, "critical": 0}


def test_dispatch_none_runs_nothing():
    calls, on_async_gc, on_critical = _record_calls()
    label = qt_psi.dispatch_psi_action(
        "none", on_async_gc=on_async_gc, on_critical=on_critical)
    assert label == "none"
    assert calls == {"async_gc": 0, "critical": 0}


def test_dispatch_critical_invokes_purge_and_maps_status():
    # The path that can't be exercised by a headless harness: CRITICAL must call the
    # purge callback (the real wiring passes _purge_renderer('psi-critical')) exactly once
    # and never the GC, and map each decision status to its telemetry label.
    for status, expected in [
        ("submitted", "purge_submitted"),
        ("skipped_ceiling", "purge_skipped_ceiling"),
        ("rate_limited", "purge_rate_limited"),
        ("anything-else", "purge_unknown"),
    ]:
        calls, on_async_gc, on_critical = _record_calls()
        on_critical.status = status
        label = qt_psi.dispatch_psi_action(
            "critical", on_async_gc=on_async_gc, on_critical=on_critical)
        assert label == expected
        assert calls == {"async_gc": 0, "critical": 1}


# --- start_psi_monitor: graceful no-op when PSI is unavailable ---

def test_monitor_noop_when_psi_absent(monkeypatch, capsys):
    import threading
    monkeypatch.setattr(qt_psi.os.path, "exists", lambda p: False)
    before = {t.name for t in threading.enumerate()}
    result = qt_psi.start_psi_monitor()
    after = {t.name for t in threading.enumerate()}
    assert result is None
    assert "psi-monitor" not in (after - before)   # no daemon thread spun up
    out = capsys.readouterr().out
    assert "PSI unavailable" in out and "disabled" in out


# --- env-tunable thresholds ---

def test_threshold_defaults():
    assert qt_psi.PSI_MODERATE == 10.0
    assert qt_psi.PSI_CRITICAL == 40.0
    assert qt_psi.PSI_FULL_CRITICAL == 5.0


def test_threshold_override_and_floor():
    assert qt_psi.psi_threshold("ODYSSEUS_PSI_MODERATE", 10.0) == 10.0
    os.environ["ODYSSEUS_PSI_MODERATE"] = "25"
    try:
        assert qt_psi.psi_threshold("ODYSSEUS_PSI_MODERATE", 10.0) == 25.0
    finally:
        del os.environ["ODYSSEUS_PSI_MODERATE"]
    os.environ["ODYSSEUS_PSI_MODERATE"] = "-5"  # floored at 0
    try:
        assert qt_psi.psi_threshold("ODYSSEUS_PSI_MODERATE", 10.0) == 0.0
    finally:
        del os.environ["ODYSSEUS_PSI_MODERATE"]
