"""Unit tests for the graduated PSI monitor logic (issue #120).

The decision/parse helpers in qt_wrapper are pure and module-level, so these are real
unit tests rather than source greps. Importing qt_wrapper needs PyQt6 (module-level
imports); skip cleanly where it is absent so a light CI still collects.
"""
import os
import pytest

qt_wrapper = pytest.importorskip(
    "qt_wrapper", reason="PyQt6 not available; logic still covered by source audit")


# --- _psi_level: harness CalculatePressureLevel boundaries ---

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
    assert qt_wrapper._psi_level(
        some, full, moderate=10.0, critical=40.0, full_critical=5.0) == expected


# --- _psi_should_emit: the three-arm notify discipline ---

def test_emit_on_level_change_up():
    assert qt_wrapper._psi_should_emit(
        "NONE", "MODERATE", now=100.0, last_emit=100.0, cooldown=30) is True


def test_moderate_sustained_waits_for_cooldown():
    # Sustained MODERATE: no re-emit before cooldown, re-emit at/after it.
    assert qt_wrapper._psi_should_emit(
        "MODERATE", "MODERATE", now=120.0, last_emit=100.0, cooldown=30) is False
    assert qt_wrapper._psi_should_emit(
        "MODERATE", "MODERATE", now=131.0, last_emit=100.0, cooldown=30) is True


def test_critical_emits_every_poll():
    # CRITICAL always notifies, even sustained and well within any cooldown.
    assert qt_wrapper._psi_should_emit(
        "CRITICAL", "CRITICAL", now=101.0, last_emit=100.0, cooldown=30) is True


def test_none_emits_only_on_down_transition():
    # Down-transition out of pressure -> emit once; staying idle -> silent (no flap).
    assert qt_wrapper._psi_should_emit(
        "MODERATE", "NONE", now=200.0, last_emit=100.0, cooldown=30) is True
    assert qt_wrapper._psi_should_emit(
        "NONE", "NONE", now=300.0, last_emit=100.0, cooldown=30) is False


# --- /proc/meminfo helpers ---

_MEMINFO = (
    "MemTotal:       16384000 kB\n"
    "MemFree:          512000 kB\n"
    "MemAvailable:     420000 kB\n"
    "SwapTotal:       4096000 kB\n"
    "SwapFree:        3200000 kB\n"
)


def test_mem_available_and_swap_used(tmp_path, monkeypatch):
    f = tmp_path / "meminfo"
    f.write_text(_MEMINFO)
    monkeypatch.setattr(qt_wrapper, "_read_meminfo_kb",
                        _meminfo_reader(str(f)))
    avail_mb, swap_mb = qt_wrapper._read_system_mem_mb()
    assert avail_mb == 420000 // 1024
    assert swap_mb == (4096000 - 3200000) // 1024


def test_meminfo_missing_keys_return_none(tmp_path, monkeypatch):
    f = tmp_path / "meminfo"
    f.write_text("MemTotal: 16384000 kB\n")  # no MemAvailable / Swap*
    monkeypatch.setattr(qt_wrapper, "_read_meminfo_kb",
                        _meminfo_reader(str(f)))
    avail_mb, swap_mb = qt_wrapper._read_system_mem_mb()
    assert avail_mb is None
    assert swap_mb is None


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


# --- /proc/pressure/memory parse ---

def test_parse_psi_avg10():
    text = ("some avg10=12.34 avg60=5.00 avg300=1.00 total=999\n"
            "full avg10=6.78 avg60=2.00 avg300=0.50 total=500\n")
    some, full = qt_wrapper._parse_psi_avg10(text)
    assert some == pytest.approx(12.34)
    assert full == pytest.approx(6.78)


def test_parse_psi_avg10_malformed_defaults_zero():
    some, full = qt_wrapper._parse_psi_avg10("garbage\n")
    assert some == 0.0 and full == 0.0


# --- env-tunable thresholds (parsed at import) ---

def test_threshold_defaults():
    assert qt_wrapper._PSI_MODERATE == 10.0
    assert qt_wrapper._PSI_CRITICAL == 40.0
    assert qt_wrapper._PSI_FULL_CRITICAL == 5.0


def test_threshold_override_and_floor():
    assert qt_wrapper._psi_threshold("ODYSSEUS_PSI_MODERATE", 10.0) == 10.0
    os.environ["ODYSSEUS_PSI_MODERATE"] = "25"
    try:
        assert qt_wrapper._psi_threshold("ODYSSEUS_PSI_MODERATE", 10.0) == 25.0
    finally:
        del os.environ["ODYSSEUS_PSI_MODERATE"]
    os.environ["ODYSSEUS_PSI_MODERATE"] = "-5"  # floored at 0
    try:
        assert qt_wrapper._psi_threshold("ODYSSEUS_PSI_MODERATE", 10.0) == 0.0
    finally:
        del os.environ["ODYSSEUS_PSI_MODERATE"]
