"""Linux PSI memory-pressure detection core (no Qt dependency).

This is the framework-agnostic detection layer: it reads /proc/pressure/memory, parses
it to stall percentages, classifies a pressure level, and runs the notify FSM, handing
each event to a single-cell queue. It names no Qt type. qt_wrapper.py is the output
adapter: it drains the queue on the Qt main thread and turns each event into an action
(async GC or renderer purge) plus the [PSI] telemetry line.

Keeping the two apart lets the detection logic be unit-tested with no PyQt/Qt runtime
(the GUI stack is a stub in the server venv), and matches the two-layer split the
companion chromium-linux-mempressure contribution uses (detection core vs. output
adapter). The level mapping and notify discipline are transliterated from that project's
harness (CalculatePressureLevel / CheckMemoryPressure).
"""
import os
import threading
import time

# Pressure levels (graduated, matching the chromium-linux-mempressure harness).
LEVEL_NONE = 'NONE'
LEVEL_MODERATE = 'MODERATE'
LEVEL_CRITICAL = 'CRITICAL'

PSI_PATH = '/proc/pressure/memory'
POLL_INTERVAL = 5     # seconds between PSI reads
COOLDOWN = 10         # MODERATE re-emit cadence; matches the harness
                      # kModeratePressureCooldown (10 s) so the log faithfully mirrors
                      # when its policy would re-notify under sustained MODERATE.
HEARTBEAT = 60        # seconds between NONE heartbeat lines


def psi_threshold(name: str, default: float) -> float:
    """Parse an env-tunable PSI threshold (avg10 stall %), floored at 0."""
    try:
        return max(0.0, float(os.environ.get(name, default)))
    except ValueError:
        return default


# Thresholds mirror the harness's "conservative, tune via field trials" defaults; this
# monitor's telemetry is how they are field-validated on real hardware.
PSI_MODERATE = psi_threshold('ODYSSEUS_PSI_MODERATE', 10.0)       # some_avg10
PSI_CRITICAL = psi_threshold('ODYSSEUS_PSI_CRITICAL', 40.0)       # some_avg10
PSI_FULL_CRITICAL = psi_threshold('ODYSSEUS_PSI_FULL_CRITICAL', 5.0)  # full_avg10

# Event cell, written by the daemon monitor on a level transition (or the slow
# heartbeat) and read and cleared by qt_wrapper's 250 ms Qt drain timer. Single-element
# list assignment is GIL-atomic so no lock is needed, which keeps the monitor off the
# Qt main thread. Record: {'level','some','full','mem_avail_mb','swap_mb','requested'}
# with requested in {'none','async_gc','critical'}.
psi_event_pending: list = [None]


def psi_level(some, full, *, moderate, critical, full_critical) -> str:
    """Map PSI avg10 stall percentages to a pressure level.

    Direct transliteration of the harness CalculatePressureLevel: CRITICAL if the
    'some' stall reaches `critical` OR the 'full' stall (every task stalled) reaches
    `full_critical`; MODERATE if 'some' reaches `moderate`; else NONE.
    """
    if some >= critical or full >= full_critical:
        return LEVEL_CRITICAL
    if some >= moderate:
        return LEVEL_MODERATE
    return LEVEL_NONE


def psi_should_emit(prev_level, level, now, last_emit, *, cooldown) -> bool:
    """The harness CheckMemoryPressure notify discipline, three distinct arms.

    One gate drives both *act* and *emit*, so the log is a faithful record of when the
    harness policy would notify (the property being field-validated):
      - NONE: only on the down-transition out of a pressure level (never while idle).
      - MODERATE: on entry, then re-emit only every `cooldown` while sustained.
      - CRITICAL: every poll (always notify). Acting is throttled downstream by the
        purge rate-limit/ceiling, and dense telemetry during a rare CRITICAL episode is
        exactly when the validation data is most wanted.
    """
    if level == LEVEL_CRITICAL:
        return True
    if level == LEVEL_MODERATE:
        if level != prev_level:
            return True
        return (now - last_emit) >= cooldown
    # level == NONE
    return prev_level != LEVEL_NONE


def read_meminfo_kb(*keys):
    """Read the named /proc/meminfo rows (kB) in one pass; missing key -> None."""
    out = {k: None for k in keys}
    try:
        with open('/proc/meminfo') as f:
            for line in f:
                field = line.split(':', 1)
                if field[0] in out:
                    out[field[0]] = int(field[1].split()[0])
    except (OSError, ValueError, IndexError):
        pass
    return out


def read_system_mem_mb():
    """One /proc/meminfo pass -> (mem_available_mb, swap_used_mb), either None.

    PSI is a *system* signal; correlating it with renderer RSS alone is a category
    error, so the telemetry pairs it with host MemAvailable. Swap used
    (SwapTotal - SwapFree) reads the reclaim path PSI rides up.
    """
    m = read_meminfo_kb('MemAvailable', 'SwapTotal', 'SwapFree')
    avail = m['MemAvailable']
    avail_mb = avail // 1024 if avail is not None else None
    if m['SwapTotal'] is None or m['SwapFree'] is None:
        swap_mb = None
    else:
        swap_mb = (m['SwapTotal'] - m['SwapFree']) // 1024
    return avail_mb, swap_mb


def parse_psi_avg10(text):
    """Parse 'some'/'full' avg10 from /proc/pressure/memory; missing -> 0.0."""
    some = full = 0.0
    for line in text.splitlines():
        parts = line.split()
        if not parts:
            continue
        try:
            if parts[0] == 'some':
                some = float(parts[1].split('=')[1])
            elif parts[0] == 'full':
                full = float(parts[1].split('=')[1])
        except (IndexError, ValueError):
            continue
    return some, full


def dispatch_psi_action(requested, *, on_async_gc, on_critical) -> str:
    """Map a drained event's `requested` action to its telemetry label, invoking the
    side-effect callbacks. The Qt/CDP work lives in the callbacks (`on_async_gc` runs the
    JS GC, `on_critical` runs the gated renderer purge and returns its decision status),
    so this control flow (including the rarely-exercised CRITICAL path) is unit-testable
    without a running renderer:

      'async_gc' -> on_async_gc();          label 'async_gc'
      'critical' -> on_critical() status;   label maps the purge decision
       otherwise -> (no side effect);       label 'none'
    """
    if requested == 'async_gc':
        on_async_gc()
        return 'async_gc'
    if requested == 'critical':
        status = on_critical()
        return {
            'submitted': 'purge_submitted',
            'skipped_ceiling': 'purge_skipped_ceiling',
            'rate_limited': 'purge_rate_limited',
        }.get(status, 'purge_unknown')
    return 'none'


def start_psi_monitor():
    """Start the daemon thread monitoring Linux PSI; no-op when PSI is unavailable.

    PSI avg10 is the fraction of time tasks stalled waiting for memory over the last
    10 s, the OS memory-pressure signal absent in embedded QtWebEngine builds. The
    monitor classifies it into NONE/MODERATE/CRITICAL, and on each transition the
    harness policy would notify on, writes a record to psi_event_pending for the Qt
    adapter to act on: MODERATE -> async JS GC, CRITICAL -> gated renderer purge. A slow
    heartbeat records the NONE trajectory of a clean session. Does no Qt work.

    Returns the started thread, or None when `/proc/pressure/memory` is absent (kernel
    < 4.20, CONFIG_PSI=n, or hidden in a container); the wrapper then runs without the
    graduated signal.
    """
    if not os.path.exists(PSI_PATH):
        # Log rather than fail silently: on a no-PSI kernel the operator should know the
        # graduated monitor is off (reclaim then relies only on the idle/focus paths).
        print(f'[MEM] PSI unavailable ({PSI_PATH} absent); '
              f'graduated pressure monitor disabled', flush=True)
        return None

    def _emit(level, some, full, requested):
        avail_mb, swap_mb = read_system_mem_mb()
        psi_event_pending[0] = {
            'level': level, 'some': some, 'full': full,
            'mem_avail_mb': avail_mb, 'swap_mb': swap_mb, 'requested': requested,
        }

    def _loop():
        prev_level = LEVEL_NONE
        last_emit = 0.0
        last_heartbeat = 0.0
        error_logged = False
        while True:
            try:
                with open(PSI_PATH) as f:
                    some, full = parse_psi_avg10(f.read())
                level = psi_level(
                    some, full, moderate=PSI_MODERATE,
                    critical=PSI_CRITICAL, full_critical=PSI_FULL_CRITICAL)
                now = time.monotonic()
                if psi_should_emit(prev_level, level, now, last_emit,
                                   cooldown=COOLDOWN):
                    requested = {
                        LEVEL_MODERATE: 'async_gc',
                        LEVEL_CRITICAL: 'critical',
                    }.get(level, 'none')
                    _emit(level, some, full, requested)
                    last_emit = now
                    last_heartbeat = now
                elif level == LEVEL_NONE and now - last_heartbeat >= HEARTBEAT:
                    _emit(LEVEL_NONE, some, full, 'none')
                    last_heartbeat = now
                prev_level = level
                error_logged = False  # a clean poll clears the error latch
            except Exception as exc:
                # Don't die or spin silently: log the first failure (and the first after
                # any recovery), then suppress repeats so a persistent fault is visible
                # without flooding the log every POLL_INTERVAL.
                if not error_logged:
                    print(f'[MEM] PSI monitor poll error '
                          f'({type(exc).__name__}: {exc}); retrying every '
                          f'{POLL_INTERVAL}s', flush=True)
                    error_logged = True
            time.sleep(POLL_INTERVAL)

    thread = threading.Thread(target=_loop, daemon=True, name='psi-monitor')
    thread.start()
    print('[MEM] PSI memory pressure monitor started (graduated)', flush=True)
    return thread
