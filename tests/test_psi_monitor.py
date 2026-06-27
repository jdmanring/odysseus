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
