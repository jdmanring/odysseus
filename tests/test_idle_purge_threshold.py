"""The sustained-idle forcible purge must only fire on a genuine away gap.

The forcible purge blocks the renderer ~1s (no async/lazy purge exists on
QtWebEngine — the only CDP reclaim is the synchronous OOM-intervention; Linux
memory-pressure eviction is a no-op). At a 3 s threshold it fired during normal
reading/thinking pauses, and a ~1s freeze landing on a click — or dropping a
mid-drag mouseup — left Chromium's left-button state stuck ("can't left-click,
right-click works"). The threshold must therefore be a real away-from-keyboard
gap, with the switched-away / minimized cases reclaimed promptly by the focus-loss
and minimize purges instead. Static assertions on qt_wrapper.py.
"""
import re
from pathlib import Path

_SRC = Path("qt_wrapper.py").read_text(encoding="utf-8")


def test_idle_threshold_is_away_from_keyboard_not_a_reading_pause():
    m = re.search(r"_IDLE_RECLAIM_AFTER_S\s*=\s*([\d.]+)", _SRC)
    assert m, "_IDLE_RECLAIM_AFTER_S not found"
    secs = float(m.group(1))
    assert secs >= 30.0, (
        f"_IDLE_RECLAIM_AFTER_S={secs}s is a reading-pause window — the blocking "
        f"purge would interrupt active use. Must be a genuine away gap (>=30s)."
    )


def test_sustained_idle_purge_gated_on_that_threshold():
    block = _SRC[_SRC.index("def _maybe_idle_purge"):][:1200]
    assert "_IDLE_RECLAIM_AFTER_S" in block
    assert "_purge_renderer('sustained-idle')" in block


def test_prompt_reclaim_paths_exist_for_leaving():
    # The "user left" cases reclaim immediately, without the idle delay.
    assert "_purge_renderer('focus-loss')" in _SRC
    assert "_purge_renderer('minimized')" in _SRC
