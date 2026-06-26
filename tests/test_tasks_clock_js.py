"""Guard: the Tasks clock updates at minute resolution and only writes on change.

Showing live seconds repainted the draggable Tasks-modal layer and churned a
detached text node every second; Qt does not evict tiles below memory pressure,
so that per-second churn accumulated (the dominant residual producer with Tasks
open). Minute resolution + a write-only-on-change guard removes the producer. #110.
"""
from pathlib import Path

_JS = (Path(__file__).resolve().parents[1] / "static/js/tasks.js").read_text(encoding="utf-8")


def _tickclock_body() -> str:
    i = _JS.index("function _tickClock()")
    return _JS[i: _JS.index("\n  }", i)]


def test_clock_is_minute_resolution_not_seconds():
    body = _tickclock_body()
    assert "second: '2-digit'" not in body, "clock must not show live seconds (per-second repaint producer)"
    assert "minute: '2-digit'" in body


def test_clock_writes_only_on_change():
    body = _tickclock_body()
    assert "if (el.textContent !== next)" in body, (
        "must skip the textContent write when unchanged so all but ~1 tick/min is a no-op"
    )
