"""Renderer-hang watchdog (issue #137): detection-core unit tests + wrapper wiring.

The detection core (qt_watchdog.HangDetector) is Qt-free and tested directly
with a fake clock. The Qt side (ping timer, pong callbacks, CDP recovery,
main-thread WebAction fallback) cannot run under the server venv's stub PyQt6,
so its wiring is locked by static analysis of qt_wrapper.py — the established
pattern for wrapper behavior (see test_qt_cdp_listener_audit.py).
"""

import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

import qt_watchdog
from qt_watchdog import HangDetector

_WRAPPER = (_REPO / "qt_wrapper.py").read_text(encoding="utf-8")


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, s):
        self.t += s


def _detector(clock, **kw):
    kw.setdefault("hang_after_s", 35.0)
    kw.setdefault("min_missed", 3)
    kw.setdefault("recovery_cooldown_s", 300.0)
    return HangDetector(now_fn=clock, **kw)


# ---------------------------------------------------------------------------
# Detection core
# ---------------------------------------------------------------------------

def test_fresh_detector_is_not_hung():
    d = _detector(FakeClock())
    assert not d.is_hung()
    assert not d.should_recover()


def test_hang_requires_both_missed_count_and_silence():
    clock = FakeClock()
    d = _detector(clock)
    # 3 missed pings but not enough silence yet
    for _ in range(3):
        d.on_ping_sent()
    clock.advance(20)
    assert not d.is_hung(), "silence below hang_after_s must not be a hang"
    # Enough silence but the missed counter was reset by a pong
    d.on_pong()
    clock.advance(100)
    assert not d.is_hung(), "silence without missed pings must not be a hang"


def test_declares_hang_after_missed_pings_and_silence():
    clock = FakeClock()
    d = _detector(clock)
    for _ in range(3):
        d.on_ping_sent()
        clock.advance(12)
    assert d.is_hung()
    assert d.should_recover()


def test_pong_resets_missed_counter():
    clock = FakeClock()
    d = _detector(clock)
    d.on_ping_sent()
    d.on_ping_sent()
    d.on_pong()
    d.on_ping_sent()
    clock.advance(100)
    assert not d.is_hung(), "pong must reset the consecutive-missed count"


def test_two_missed_pings_never_hang():
    clock = FakeClock()
    d = _detector(clock)
    d.on_ping_sent()
    d.on_ping_sent()
    clock.advance(1000)
    assert not d.is_hung()


def test_recovery_cooldown_blocks_immediate_second_recovery():
    clock = FakeClock()
    d = _detector(clock)
    for _ in range(3):
        d.on_ping_sent()
        clock.advance(12)
    assert d.should_recover()
    d.record_recovery()
    # Renderer wedges again straight after the reload
    for _ in range(3):
        d.on_ping_sent()
        clock.advance(12)
    assert d.is_hung()
    assert not d.should_recover(), "cooldown must block a reload loop"
    clock.advance(300)
    assert d.should_recover(), "cooldown expiry must re-enable recovery"


def test_record_recovery_grants_fresh_grace():
    clock = FakeClock()
    d = _detector(clock)
    for _ in range(3):
        d.on_ping_sent()
        clock.advance(12)
    d.record_recovery()
    assert not d.is_hung(), "recovery must reset missed count and silence"
    assert d.silence_s() == 0


def test_startup_grace_counts_construction_as_pong():
    clock = FakeClock()
    d = _detector(clock)
    assert d.silence_s() == 0


def test_default_thresholds_are_sane():
    # 3 pings at the 10 s interval span 30 s < HANG_AFTER_S, so the silence
    # condition (not just the count) always gates the declaration.
    assert qt_watchdog.MIN_MISSED_PINGS * qt_watchdog.PING_INTERVAL_S \
        < qt_watchdog.HANG_AFTER_S + qt_watchdog.PING_INTERVAL_S
    assert qt_watchdog.RECOVERY_COOLDOWN_S >= 60


# ---------------------------------------------------------------------------
# Wrapper wiring (static analysis — Qt not importable in the server venv)
# ---------------------------------------------------------------------------

def test_wrapper_imports_watchdog():
    assert re.search(r"^import qt_watchdog$", _WRAPPER, re.M)


def test_wrapper_creates_detector_and_timer():
    assert "qt_watchdog.HangDetector()" in _WRAPPER
    assert "qt_watchdog.PING_INTERVAL_S" in _WRAPPER
    assert "_hang_timer" in _WRAPPER


def test_ping_pairs_sent_with_runjavascript_pong():
    # on_ping_sent must be immediately followed by the runJavaScript ping whose
    # callback records the pong.
    m = re.search(
        r"on_ping_sent\(\)\s*\n\s*page\.runJavaScript\('1',"
        r" lambda _r: self\._hang_detector\.on_pong\(\)\)",
        _WRAPPER,
    )
    assert m, "ping bookkeeping and the JS ping must be paired"


def test_recovery_uses_cdp_page_reload_off_main_thread():
    assert "_cdp_call('Page.reload')" in _WRAPPER
    assert "_cdp_executor.submit(_hang_recover_cdp)" in _WRAPPER


def test_silence_is_read_before_recovery_reset():
    # record_recovery() resets the pong clock; the [HANG] line must read
    # silence_s() first or it always logs "unresponsive 0s" (seen live in the
    # SIGSTOP validation run).
    tick = _WRAPPER[_WRAPPER.index("def _hang_tick"):]
    tick = tick[:tick.index("self._hang_timer")]
    assert tick.index("_silence = self._hang_detector.silence_s()") \
        < tick.index("self._hang_detector.record_recovery()")


def test_recovery_is_recorded_before_reload():
    # record_recovery() must run when should_recover() fires, or the next tick
    # fires a second recovery before the first finishes.
    body = _WRAPPER[_WRAPPER.index("def _hang_tick"):]
    body = body[:body.index("self._hang_timer")]
    assert body.index("record_recovery()") < body.index("_cdp_executor.submit")


def test_cdp_failure_falls_back_to_webaction_on_main_thread():
    # triggerAction is a Qt call: it must happen inside _hang_tick (main
    # thread), never inside the executor-submitted recovery function.
    tick = _WRAPPER[_WRAPPER.index("def _hang_tick"):]
    tick = tick[:tick.index("self._hang_timer")]
    assert "triggerAction(QWebEnginePage.WebAction.Reload)" in tick
    recover = _WRAPPER[_WRAPPER.index("def _hang_recover_cdp"):]
    recover = recover[:recover.index("def _hang_tick")]
    assert "triggerAction" not in recover


def test_dead_renderer_skips_hang_judgement():
    # renderProcessPid() is None while crashed/respawning — that path belongs
    # to renderProcessTerminated; the watchdog must not double-fire.
    tick = _WRAPPER[_WRAPPER.index("def _hang_tick"):]
    tick = tick[:tick.index("self._hang_timer")]
    assert "renderProcessPid() is None" in tick


def test_load_finished_counts_as_pong():
    assert "loadFinished.connect" in _WRAPPER
    lf = _WRAPPER[_WRAPPER.index("loadFinished.connect"):]
    assert "on_pong()" in lf[:200]
