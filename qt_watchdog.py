"""Renderer-hang detection core (Qt-free, unit-testable).

QtWebEngine exposes no hung-renderer signal: renderProcessTerminated fires
only when the renderer process dies, while a main-thread deadlock (observed
live: pthread_cond_wait inside libQt6WebEngineCore, zero JS execution
contexts, hover highlights still painting because the GPU compositor is
alive) leaves the process running and the signal silent. The only reliable
liveness probe is a runJavaScript ping — its callback is serviced by the
renderer main thread, so a wedged main thread simply never answers.

HangDetector holds the bookkeeping only: the wrapper reports pings sent and
pongs received, and asks should_recover() whether enough consecutive pings
have gone unanswered for long enough to force a recovery. Recovery is
rate-limited so a renderer that wedges again straight after a reload cannot
thrash in a reload loop. No Qt imports here — the module must be testable
under the server venv, whose PyQt6 is a stub.
"""

import time

PING_INTERVAL_S = 10.0        # wrapper timer period between pings
HANG_AFTER_S = 35.0           # minimum silence before declaring a hang
MIN_MISSED_PINGS = 3          # consecutive unanswered pings required
RECOVERY_COOLDOWN_S = 300.0   # minimum gap between forced recoveries


class HangDetector:
    """Consecutive-missed-ping hang detector with recovery rate limiting.

    Both conditions must hold to declare a hang: at least ``min_missed``
    pings unanswered *and* at least ``hang_after_s`` of silence. The pair
    makes a single dropped callback or a long-but-alive main-thread task
    (large session render) insufficient on its own.
    """

    def __init__(self, hang_after_s=HANG_AFTER_S, min_missed=MIN_MISSED_PINGS,
                 recovery_cooldown_s=RECOVERY_COOLDOWN_S, now_fn=time.monotonic):
        self._hang_after = float(hang_after_s)
        self._min_missed = int(min_missed)
        self._cooldown = float(recovery_cooldown_s)
        self._now = now_fn
        # Startup grace: treat construction as a pong so a slow first load
        # never counts as silence.
        self._last_pong = self._now()
        self._missed = 0
        self._last_recovery = None

    def on_ping_sent(self):
        self._missed += 1

    def on_pong(self):
        self._missed = 0
        self._last_pong = self._now()

    def silence_s(self):
        return self._now() - self._last_pong

    def is_hung(self):
        return (self._missed >= self._min_missed
                and self.silence_s() >= self._hang_after)

    def should_recover(self):
        """True when hung and outside the recovery cooldown.

        A caller that acts on this must call record_recovery() immediately,
        otherwise the next tick fires a second recovery.
        """
        if not self.is_hung():
            return False
        if (self._last_recovery is not None
                and (self._now() - self._last_recovery) < self._cooldown):
            return False
        return True

    def record_recovery(self):
        self._last_recovery = self._now()
        # The reload tears down the wedged renderer; grant the replacement a
        # full grace period before it can be judged again.
        self._missed = 0
        self._last_pong = self._now()
