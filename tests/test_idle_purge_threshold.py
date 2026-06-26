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


def test_idle_threshold_default_meets_the_idle_detection_standard():
    # The W3C/WICG Idle Detection API mandates a 60s MINIMUM to call a user idle;
    # below that you are measuring a pause, not idle. Tunable via the env var, but
    # the shipped DEFAULT must follow the standard, not a guessed number.
    m = re.search(r"os\.environ\.get\('ODYSSEUS_IDLE_RECLAIM_S',\s*'([\d.]+)'\)", _SRC)
    assert m, "ODYSSEUS_IDLE_RECLAIM_S default not found"
    secs = float(m.group(1))
    assert secs >= 60.0, (
        f"default {secs}s is below the Idle Detection API's 60s idle minimum — "
        f"the blocking purge would fire on a pause, not a genuine away gap."
    )


def test_sustained_idle_purge_gated_on_that_threshold():
    block = _SRC[_SRC.index("def _maybe_idle_purge"):][:1200]
    assert "_IDLE_RECLAIM_AFTER_S" in block
    assert "_purge_renderer('sustained-idle')" in block


def test_prompt_reclaim_paths_exist_for_leaving():
    # The "user left" cases reclaim immediately, without the idle delay.
    assert "_purge_renderer('focus-loss')" in _SRC
    assert "_purge_renderer('minimized')" in _SRC
