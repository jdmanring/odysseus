import json
import os
import re as _re
import sys
import time as _time

# ==============================================================================
# CRITICAL: Logging setup must happen BEFORE any PyQt6/QtWebEngine imports.
#
# sys.stdout/stderr alone is not enough; Chromium renderer subprocesses inherit
# OS-level file descriptors (fd 1, fd 2), not Python's sys.stdout/stderr.
# os.dup2 replaces the OS fds so all child process output lands in our log.
# ==============================================================================
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# Rotate logs at startup rather than mid-run: once os.dup2 binds the Chromium
# renderer's inherited fds to the log inode, the file cannot be swapped while
# the process lives. Renaming before the open+dup2 avoids that constraint.
# Constants match src/constants.py (LOG_MAX_BYTES, LOG_BACKUP_COUNT) so all
# three log files follow the same retention policy.
_LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MB, matches app RotatingFileHandler
_LOG_BACKUP_COUNT = 5               # matches app LOG_BACKUP_COUNT


def _rotate_log(path: str) -> None:
    """Shift existing backups and rename path → path.1 if over _LOG_MAX_BYTES.

    Mirrors the behaviour of logging.handlers.RotatingFileHandler with
    backupCount=_LOG_BACKUP_COUNT. Silent on any error.
    """
    try:
        if os.path.getsize(path) <= _LOG_MAX_BYTES:
            return
        # Shift: path.4 → path.5, path.3 → path.4, ..., path.1 → path.2
        for n in range(_LOG_BACKUP_COUNT, 1, -1):
            src = f'{path}.{n - 1}'
            dst = f'{path}.{n}'
            if os.path.exists(src):
                if os.path.exists(dst):
                    os.remove(dst)
                os.rename(src, dst)
        # Move current log to path.1
        backup = path + '.1'
        if os.path.exists(backup):
            os.remove(backup)
        os.rename(path, backup)
    except OSError:
        pass


_rotate_log(os.path.join(LOG_DIR, "wrapper_system.log"))
_log_file = open(os.path.join(LOG_DIR, "wrapper_system.log"), "a", buffering=1)
sys.stdout.flush()
sys.stderr.flush()
os.dup2(_log_file.fileno(), 1)   # redirect fd 1: Chromium renderer stdout → our log
os.dup2(_log_file.fileno(), 2)   # redirect fd 2: Chromium renderer stderr → our log
sys.stdout = _log_file
sys.stderr = _log_file
print(f'[LOG] wrapper_system.log opened at {_time.strftime("%Y-%m-%dT%H:%M:%S")}',
      flush=True)

# macOS: Qt WebEngine rides Metal (via ANGLE) on Qt 6.5+, on both arm64 and
# x86_64. None of the Linux wrapper's GBM/zero-copy/NVIDIA branching applies
# here, but GPU-less machines (VMs — macOS guests get no paravirtual GPU) DO
# need detection: forcing GPU rasterization onto the SwiftShader fallback
# churns a CPU-emulated GPU per frame and shows up as flicker/lag and glitched
# repaints (observed live on the Tahoe bench). Every real Mac GPU (Intel, AMD,
# Apple silicon) registers an IOAccelerator subclass in the IO registry, so an
# empty `ioreg -rc IOAccelerator` (~15 ms, once at startup) is the reliable
# no-Metal-device signal. Fail-safe: any probe error reads as "has GPU" so a
# glitch never degrades a real machine.
import subprocess


def _macos_software_render() -> bool:
    """True when no Metal-capable accelerator exists (SwiftShader fallback)."""
    try:
        r = subprocess.run(["ioreg", "-rc", "IOAccelerator"],
                           capture_output=True, timeout=5)
        return not r.stdout.strip()
    except Exception:
        return False


_software_render = _macos_software_render()

_gpu_flags = [] if _software_render else [
    "--ignore-gpu-blocklist",
    "--enable-gpu-rasterization",
]
# WebGPU is pointless on SwiftShader and adds feature surface; keep it only
# where a real GPU backs it.
_features = "SharedArrayBuffer,PartitionAllocMemoryReclaimer,BlinkHeapCompaction"
if not _software_render:
    _features = "WebGPU," + _features

os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join([
    "--no-sandbox",
    *_gpu_flags,
    f"--enable-features={_features}",
    "--enable-logging=stderr --log-level=1",  # captured via os.dup2 into wrapper_system.log
    "--remote-debugging-port=9222",            # Chrome DevTools at http://localhost:9222
    # --minor-ms, not --minor-mc: V8 renamed the minor-GC flag (MinorMC → MinorMS)
    # in the V8 shipped with Qt 6.11's Chromium; the old name logs "Error:
    # unrecognized flag" at renderer start (non-fatal, but the flag is dropped).
    "--js-flags=--expose-gc,--initial-old-space-size=128,--max-old-space-size=512,--optimize-for-size,--minor-ms",
    "--renderer-process-limit=1",
    "--disable-extensions",
    # NB: low-end-device-mode (the Chromium flag) is deliberately NOT set. It
    # caused a lighter-rectangle raster tint on dark themes and did not bound the
    # actual OOM — Oilpan detached-DOM churn, a separate pool from the raster
    # tile budget. See jdmanring/odysseus#96.
])

import concurrent.futures as _futures
import ctypes
import signal
import socket as _cdp_sock
import struct as _cdp_struct
import base64 as _cdp_b64
import urllib.request as _cdp_req
import threading as _threading
import time
from PyQt6.QtWidgets import QApplication, QMainWindow, QColorDialog
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import (
    QWebEngineProfile, QWebEnginePage, QWebEngineScript, QWebEngineSettings,
)
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtCore import Qt, QUrl, QObject, QFile, QIODevice, QTimer, QSettings, QEvent, pyqtSlot, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QColor, QIcon, QAction, QKeySequence
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

INSTALL_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_PYTHON = os.path.join(INSTALL_DIR, "venv", "bin", "python")
PORT = os.environ.get("APP_PORT", "7000")
WINDOW_TITLE = "Odysseus"
PROFILE_NAME = "odysseus"


def _theme_bg_color() -> QColor:
    """Read the saved theme background from data/user_prefs.json.

    setBackgroundColor() sets the QWebEnginePage compositor base-background
    colour, what shows in any brief gap before content paints. Hardcoding
    #282c34 (the default theme) would flash lighter than the actual background
    on a custom dark theme (e.g. Catppuccin #1e1e2e); reading the persisted bg
    at startup keeps the base colour in sync with the user's real theme.
    """
    try:
        prefs_path = os.path.join(INSTALL_DIR, 'data', 'user_prefs.json')
        with open(prefs_path, encoding='utf-8') as f:
            prefs = json.load(f)
        for user_data in prefs.get('_users', {}).values():
            bg = user_data.get('theme', {}).get('colors', {}).get('bg', '')
            if bg and bg.startswith('#') and len(bg) == 7:
                r, g, b = int(bg[1:3], 16), int(bg[3:5], 16), int(bg[5:7], 16)
                return QColor(r, g, b)
    except Exception:
        pass
    return QColor(0x28, 0x2c, 0x34)  # default Odysseus dark theme


# macOS conventions: Application Support for data, Caches for cache.
DATA_DIR = os.path.expanduser("~/Library/Application Support/odysseus/webengine")
CACHE_DIR = os.path.expanduser("~/Library/Caches/odysseus/webengine")

_UVICORN_PATTERN = "uvicorn app:app"
_server_proc = None


def kill_zombies():
    result = subprocess.run(["pkill", "-f", _UVICORN_PATTERN], check=False)
    if result.returncode == 0:
        print("Killed stale uvicorn process(es), waiting for port to release...")
        time.sleep(1)


def start_server():
    global _server_proc
    print(f"Starting Odysseus server on port {PORT}...")
    # --no-access-log: uvicorn's access log defaults to ON, emitting one log line
    # per HTTP request. For this embedded, localhost, single-user deployment the
    # always-on UI polls (email/tasks/calendar) would churn that log forever with
    # no operator reading it; errors still surface via server.log. Startup banners
    # and tracebacks still reach server_access.log via the subprocess stdout/stderr.
    cmd = [VENV_PYTHON, "-m", "uvicorn", "app:app",
           "--host", "127.0.0.1", "--port", PORT, "--no-access-log"]
    env = os.environ.copy()
    env["ODYSSEUS_LOG_FILE"] = os.path.join(LOG_DIR, "server.log")
    _rotate_log(os.path.join(LOG_DIR, "server_access.log"))
    _access_log = open(os.path.join(LOG_DIR, "server_access.log"), "a", buffering=1)
    _server_proc = subprocess.Popen(
        cmd,
        cwd=INSTALL_DIR,
        env=env,
        stdout=_access_log,
        stderr=_access_log,
        start_new_session=True,
    )
    for _ in range(30):
        try:
            import urllib.request
            urllib.request.urlopen(f"http://localhost:{PORT}", timeout=1)
            print("Server ready.")
            return True
        except Exception:
            time.sleep(0.5)
    print("Server slow to start, proceeding anyway.")
    return False


def stop_server():
    global _server_proc
    print("Stopping server...")
    if _server_proc is not None:
        try:
            _server_proc.terminate()
            _server_proc.wait(timeout=5)
        except Exception:
            try:
                _server_proc.kill()
            except Exception:
                pass
        _server_proc = None
    _cdp_executor.shutdown(wait=False, cancel_futures=True)
    subprocess.run(["pkill", "-f", _UVICORN_PATTERN], check=False)
    print("Server stopped.")


def _signal_handler(sig, frame):
    # SIGTERM/SIGINT (e.g. a relaunch killing the old instance). Stop the server,
    # then HARD-EXIT rather than sys.exit: letting the interpreter unwind runs
    # Qt's QWebEngineView teardown, which intermittently null-derefs in
    # setVisible on CrBrowserMain (Qt 6.11) and logs a spurious crash. Nothing
    # meaningful is lost — the persistent profile flushes as it changes.
    stop_server()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)


def _cdp_ws_call(ws_url, method, params=None):
    """Send one CDP command to an already-resolved ws:// URL and return the result.

    Shared by _cdp_call (page target) and _cdp_browser_call (browser target).
    Returns the CDP result dict or None on any error.
    """
    try:
        hostpath = ws_url[len('ws://'):]
        host_port, path = hostpath.split('/', 1)
        host_name, port_s = host_port.split(':')
        s = _cdp_sock.create_connection((host_name, int(port_s)), timeout=2)
        try:
            key = _cdp_b64.b64encode(os.urandom(16)).decode()
            s.sendall((
                f'GET /{path} HTTP/1.1\r\nHost: {host_port}\r\n'
                'Upgrade: websocket\r\nConnection: Upgrade\r\n'
                f'Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n'
            ).encode())
            buf = b''
            while b'\r\n\r\n' not in buf:
                buf += s.recv(4096)
            if b' 101 ' not in buf.split(b'\r\n')[0]:
                return None
            payload_obj = {'id': 1, 'method': method}
            if params:
                payload_obj['params'] = params
            msg = json.dumps(payload_obj).encode()
            mask = os.urandom(4)
            masked = bytes(b ^ mask[i % 4] for i, b in enumerate(msg))
            frame_len = len(msg)
            length_byte = 0x7E if frame_len > 125 else frame_len
            header = bytes([0x81, 0x80 | length_byte])
            if frame_len > 125:
                header += _cdp_struct.pack('!H', frame_len)
            s.sendall(header + mask + masked)
            hdr = b''
            while len(hdr) < 2:
                hdr += s.recv(2 - len(hdr))
            dlen = hdr[1] & 0x7F
            if dlen == 126:
                lb = b''
                while len(lb) < 2:
                    lb += s.recv(2 - len(lb))
                dlen = _cdp_struct.unpack('!H', lb)[0]
            data = b''
            while len(data) < dlen:
                data += s.recv(dlen - len(data))
            return json.loads(data.decode()).get('result')
        finally:
            s.close()
    except Exception:
        return None


def _cdp_call(method, params=None):
    """One-shot CDP call on the page target via stdlib WebSocket.

    Embedded Chromium builds (PyQt, Electron, native wrappers) do not receive OS
    memory-pressure signals that would trigger Oilpan's automatic GC, so Python-side
    CDP calls are the reliable way to invoke collection without --expose-gc.
    Returns the CDP result dict or None on any error.
    """
    try:
        raw = _cdp_req.urlopen('http://localhost:9222/json', timeout=1).read()
        pages = json.loads(raw)
        ws_url = next(
            (p['webSocketDebuggerUrl'] for p in pages if p.get('type') == 'page'),
            None,
        )
        if not ws_url:
            return None
        return _cdp_ws_call(ws_url, method, params)
    except Exception:
        return None


# ── macOS memory reads (pure ctypes; NO ps/vm_stat subprocesses) ──────────────────
# ps and vm_stat cost a process spawn per sample and need text parsing. The kernel
# already exposes the same numbers in-process: proc_pid_rusage() gives per-pid
# resident size (the VmRSS analogue) and lifetime max phys footprint (the VmPeak
# analogue), and sysctl hw.memsize / kern.memorystatus_vm_pressure_level give
# system totals and the OS pressure level. All verified live on macOS 26 (Tahoe):
# resident_size matched `ps -o rss` within 0.1%.
_libc = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)

# rusage_info_v4 layout: 16-byte uuid then packed uint64 fields (resource.h).
# Indices below are uint64 offsets after the uuid.
_RUSAGE_INFO_V4 = 4
_RI_RESIDENT_SIZE = 6              # bytes
_RI_PHYS_FOOTPRINT = 7             # bytes (what Activity Monitor's "Memory" shows)
_RI_LIFETIME_MAX_PHYS_FOOTPRINT = 28  # bytes, v4+ only


def _sysctl_u64(name: str):
    """Read a 64-bit sysctl by name, or None on failure."""
    try:
        val = ctypes.c_uint64(0)
        size = ctypes.c_size_t(8)
        if _libc.sysctlbyname(name.encode(), ctypes.byref(val),
                              ctypes.byref(size), None, 0) == 0:
            return val.value
    except Exception:
        pass
    return None


def _sysctl_u32(name: str):
    """Read a 32-bit sysctl by name, or None on failure."""
    try:
        val = ctypes.c_uint32(0)
        size = ctypes.c_size_t(4)
        if _libc.sysctlbyname(name.encode(), ctypes.byref(val),
                              ctypes.byref(size), None, 0) == 0:
            return val.value
    except Exception:
        pass
    return None


def _mac_process_mem_kb(pid):
    """(resident kB, phys_footprint kB, lifetime_max_footprint kB) for pid,
    or (0, 0, 0) on failure.

    proc_pid_rusage works cross-pid for same-uid processes, which covers the
    renderer (our child). No task_for_pid entitlement needed.
    """
    try:
        buf = (ctypes.c_uint64 * 64)()  # 512 B, > sizeof(rusage_info_v4)
        if _libc.proc_pid_rusage(int(pid), _RUSAGE_INFO_V4, buf) == 0:
            u64 = ctypes.cast(buf, ctypes.POINTER(ctypes.c_uint64))
            base = 2  # skip the 16-byte uuid
            return (u64[base + _RI_RESIDENT_SIZE] // 1024,
                    u64[base + _RI_PHYS_FOOTPRINT] // 1024,
                    u64[base + _RI_LIFETIME_MAX_PHYS_FOOTPRINT] // 1024)
    except Exception:
        pass
    return (0, 0, 0)


# Purge reasons driven by genuine memory pressure. These bypass the busy-page
# gate below: when the host is nearly out of memory, a possible renderer crash
# (which auto-reloads) beats a host OOM kill (which takes the whole app down).
_PURGE_PRESSURE_REASONS = frozenset({'psi-critical', 'low-memory', 'node-threshold'})

# Busy-page probe: input-idle is NOT page-idle. The renderer segfaulted three
# times on 2026-07-19 (exit=11), each immediately after a forcible purge fired
# while a model download was repainting the cookbook card — no mouse/keyboard
# input, so every idle timer considered the page quiescent. Ask the page itself:
# cookbookRunning.js persists its task list in localStorage ('cookbook-tasks'),
# so an active download or a serve that is still starting up is visible here
# without any new JS-side wiring.
_BUSY_TASKS_JS = (
    "(()=>{try{const t=JSON.parse(localStorage.getItem('cookbook-tasks'))||[];"
    "return t.some(x=>x&&((x.type==='download'&&(x.status==='running'||x.status==='queued'))"
    "||(x.type==='serve'&&x.status==='running')))}catch(e){return false}})()"
)


def _renderer_busy():
    """True when the page reports an active download/starting serve.

    Runs on the CDP executor thread (socket I/O). Fails open (False) so a CDP
    hiccup can never permanently disable memory reclaim.
    """
    res = _cdp_call('Runtime.evaluate',
                    {'expression': _BUSY_TASKS_JS, 'returnByValue': True})
    try:
        return bool(res['result']['value'])
    except (TypeError, KeyError):
        return False


# Pattern that chatHistory.js emits at the end of each Phase 2 eviction batch.
_RE_EVICT = _re.compile(r'\[chatHistory\] Phase 2 evict: removed (\d+) live nodes')

# Bounds CDP background work to eviction audit threads (5 s sleep each).
_cdp_executor = _futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix='cdp')

# Renderer reclaim policy (issue #106). simulatePressureNotification is a no-op on
# QtWebEngine; Memory.forciblyPurgeJavaScriptMemory actually reclaims the renderer
# cache (measured 5.2 GB and 3.7 GB freed in single calls). The purge causes a ~1s
# stutter, so it is only ever fired off the interaction path (mouse-idle,
# focus-loss), gated by an RSS ceiling so light use never stutters, and rate-limited
# so it cannot repeat back to back.

# ── Capability detection: Rung 1 (docs/fork/low-resource-profile-design.md) ────────
# Pick the DEFAULT reclaim profile from device capability. MACOS-ONLY signals; this
# is the macOS wrapper; qt_wrapper.py / windows_wrapper.py carry their own platform
# equivalents. An explicit ODYSSEUS_* env var always overrides this (Rung 0). FAIL-
# SAFE: any read error yields the STANDARD (capable) profile, so a glitch never
# degrades a good machine; a misread low-RAM box is covered by the env override.
_LOW_RAM_GB = 2.0  # ≤ this ⇒ constrained (aligns with Android isLowRamDevice / IsLowEndDevice)

def _classify_resources(mem_total_gb, software_render):
    """Pure mapping: (mem_total_gb|None, software_render) -> (is_low_resource, reason)."""
    reasons = []
    if mem_total_gb is not None and mem_total_gb <= _LOW_RAM_GB:
        reasons.append(f'RAM {mem_total_gb:.1f} GB')
    if software_render:
        reasons.append('software render')
    return (bool(reasons), ', '.join(reasons) or 'capable')

def _macos_total_ram_gb():
    mem = _sysctl_u64('hw.memsize')
    if mem is not None:
        return mem / (1024 ** 3)
    return None

# Software-render signal comes from the pre-flag IOAccelerator probe at the top
# of this file (no Metal device ⇒ SwiftShader): the same probe that strips the
# GPU-rasterization flags also selects the constrained reclaim profile here.
_low_resource, _profile_reason = _classify_resources(_macos_total_ram_gb(), _software_render)

# RSS ceiling: the renderer is only purged above this. Measured working set after a
# purge is ~430 MB, so the off-interaction reclaim sawtooth stays ~0.43 GB → ceiling.
# Default ~1.2 GB (a safety net; with producers eliminated the renderer rarely
# approaches it). Tunable via ODYSSEUS_PURGE_CEILING_MB: lower it on RAM-constrained
# machines for a tighter cap (purges fire sooner/more often, the right trade when
# system swap/compressor churn is worse than an occasional off-interaction stutter;
# this is the "adaptive loading" response to a low-resource device; see docs/fork/
# low-resource-profile-design.md). Floored at 512 MB (just above the working set, so
# the ceiling can never sit below it and cause constant purging).
try:
    _PURGE_RSS_CEILING_KB = max(512, int(float(os.environ.get(
        'ODYSSEUS_PURGE_CEILING_MB', '700' if _low_resource else '1200')))) * 1024
except ValueError:
    _PURGE_RSS_CEILING_KB = 1_200_000
_PURGE_MIN_INTERVAL_S = 15
# Seconds of no input (mouse OR keyboard) before the *sustained-idle* reclaim may
# fire. The purge blocks the renderer ~1s and there is NO lazy/async purge on
# QtWebEngine (the only CDP reclaim is the synchronous OOM-intervention; the
# memory-pressure eviction is a no-op; see research). So this must only fire on a
# genuine away-from-keyboard gap: a short reading/thinking pause must NOT trigger
# it. At 3 s it fired constantly during normal use, and a ~1s freeze landing on a
# click, or dropping a mid-drag mouseup, left Chromium's left-button state stuck
# ("can't left-click, right-click works"). The prompt-reclaim-on-leave cases are
# handled separately and without this delay by the focus-loss and minimize purges.
# Default = 60 s, the established standard: the W3C/WICG Idle Detection API
# restricts its idle threshold to a MINIMUM of 60 s; below that you are measuring
# a pause, not idle (short thresholds are unreliable for "idle" and even leak
# typing cadence, hence the spec floor). Best-practice range is 30–120 s; 60 s is
# the principled safe choice for a *disruptive* (blocking) reclaim.
# Tunable via ODYSSEUS_IDLE_RECLAIM_S for users who deliberately want more
# aggressive reclaim (lower) and accept the stutter risk. Floored at 2 s.
try:
    _IDLE_RECLAIM_AFTER_S = max(2.0, float(os.environ.get(
        'ODYSSEUS_IDLE_RECLAIM_S', '20' if _low_resource else '60')))
except ValueError:
    _IDLE_RECLAIM_AFTER_S = 60.0

# Renderer-hang detection core (issue #137). The Qt-free bookkeeping lives in
# qt_watchdog.py so it is unit-testable under the server venv's stub PyQt6;
# this file only wires pings/pongs and performs the recovery. (qt_psi is NOT
# imported here: PSI is a Linux kernel interface; the macOS pressure signal
# is the memorystatus sysctl below.)
import qt_watchdog

# Log the selected profile once (diagnosable; notes when an env var overrode it).
_profile_overridden = bool(
    {'ODYSSEUS_IDLE_RECLAIM_S', 'ODYSSEUS_PURGE_CEILING_MB'} & os.environ.keys())
print(f"[PROFILE] {'low-resource' if _low_resource else 'standard'} ({_profile_reason}): "
      f"idle={_IDLE_RECLAIM_AFTER_S:.0f}s ceiling={_PURGE_RSS_CEILING_KB // 1024}MB"
      f"{' [env override]' if _profile_overridden else ''}", flush=True)

# Pressure event cell, written by the memorystatus monitor thread and drained on
# the Qt main thread by the 250 ms drain timer (the same cross-thread dispatch
# pattern qt_wrapper.py uses for PSI events: QTimer.singleShot from a daemon
# thread has no event loop to fire on, so a polled cell is the correct hand-off).
# Single-element list assignment is GIL-atomic so no lock is needed. Holds the
# pressure level (2=warning, 4=critical) or None when no event is pending.
_pressure_event_pending: list = [None]

# kern.memorystatus_vm_pressure_level values (xnu kern_memorystatus.h).
_MACOS_PRESSURE_NORMAL = 1
_MACOS_PRESSURE_WARNING = 2
_MACOS_PRESSURE_CRITICAL = 4


def _start_macos_memory_monitor():
    """Background thread watching macOS memory pressure via the memorystatus sysctl.

    kern.memorystatus_vm_pressure_level is the same graduated signal (normal /
    warning / critical) that dispatch_source memory-pressure sources deliver —
    readable unprivileged with one cheap in-process sysctl, no libdispatch
    machinery and no vm_stat subprocess per sample (the previous design here
    spawned vm_stat every 5 s and parsed its text output). This is the macOS
    equivalent of the OS memory-pressure signal that Chromium's browser process
    receives in a normal installation but that does not reach the renderer
    sandbox in embedded QtWebEngine builds.

    The thread only records the elevated level into _pressure_event_pending; the
    Qt-side drain timer maps warning → async JS GC and critical → the shared
    _purge_renderer gate, so sustained pressure cannot repeat-purge every poll —
    the RSS ceiling and rate limit apply exactly as they do to every other
    reclaim trigger. After signalling, the thread backs off a full 30 s (the
    level stays elevated while pressure persists, and the gated decision already
    happened on the Qt side).
    """
    _POLL_S = 5
    _BACKOFF_S = 30

    def _loop():
        if _sysctl_u32('kern.memorystatus_vm_pressure_level') is None:
            print('[MEM] macOS: memorystatus pressure sysctl unavailable', flush=True)
            return
        print('[MEM] macOS memory pressure monitor active', flush=True)
        while True:
            level = _sysctl_u32('kern.memorystatus_vm_pressure_level')
            if level is not None and level >= _MACOS_PRESSURE_WARNING:
                _pressure_event_pending[0] = level
                _time.sleep(_BACKOFF_S)
            else:
                _time.sleep(_POLL_S)

    _threading.Thread(target=_loop, daemon=True, name='macos-mem-monitor').start()


def _cdp_audit_listeners(n_evicted: int) -> None:
    """Measure jsEventListeners delta 5 s after a Phase 2 eviction batch.

    Runs in a background thread. Captures the listener count immediately before
    sleeping (pre-GC baseline), forces a collection, then reads again. The forced
    GC is what makes the delta meaningful: without it V8 may not have collected
    the evicted nodes yet, and a delta of 0 is ambiguous between "listeners
    retained" and "garbage not collected yet" (measured live 2026-07-19: delta
    stayed 0 for 12+ s after evicting 61 nodes, then dropped 430 listeners the
    moment a major GC ran). After the forced GC, a delta ≈ 0 with interactive
    nodes evicted indicates listener retention; a proportional drop confirms
    the WeakRef closures released cleanly.
    """
    pre = _cdp_call('Memory.getDOMCounters')
    pre_listeners = pre.get('jsEventListeners', 0) if pre else None
    _time.sleep(5)
    # Force a collection so the post-read reflects reachability, not GC timing.
    _cdp_call('HeapProfiler.collectGarbage')
    post = _cdp_call('Memory.getDOMCounters')
    if post and pre_listeners is not None:
        post_listeners = post.get('jsEventListeners', 0)
        delta = pre_listeners - post_listeners
        print(
            f'[CDP] post-evict listeners:'
            f' before={pre_listeners} after={post_listeners}'
            f' delta={delta} nodes-evicted={n_evicted}',
            flush=True,
        )


class NativeBridge(QObject):
    """Python-to-JS bridge exposed via QWebChannel.

    On macOS, QColorDialog.getColor() delegates to NSColorPanel — the native
    macOS color picker. No DBus/XDG portal needed.

    EXCEPT on software-render machines (no Metal device — VMs, remote sessions):
    NSColorPanel's eyedropper spawns the ColorSampler XPC service, whose window
    capture drives WindowServer through SkyLight's SOFTWARE capture path
    (CaptureSurfaceSW::Populate), which aborts — killing WindowServer and the
    whole login session (crash reports 2026-07-20: ColorSampler SIGILL →
    WindowServer SIGABRT in WSCompositeDestinationCreateWithIOSurface). There,
    eyedropperInPage tells the page to sample itself: JS overlays a crosshair
    and calls samplePagePixel(x, y); we read the pixel from view.grab() — Qt's
    own offscreen widget render, zero WindowServer capture involvement.
    """
    colorPicked = pyqtSignal(str)
    eyedropperInPage = pyqtSignal()

    def __init__(self, view=None, parent=None):
        super().__init__(parent)
        self._view = view

    @pyqtSlot()
    def openColorPicker(self):
        if _software_render and self._view is not None:
            self.eyedropperInPage.emit()
            return
        color = QColorDialog.getColor()
        self.colorPicked.emit(color.name() if color.isValid() else '')

    @pyqtSlot(float, float)
    def samplePagePixel(self, x, y):
        """Resolve an in-page eyedropper click: (x, y) are CSS px in the viewport,
        which map 1:1 to widget-logical px; view.grab() returns a device-pixel
        pixmap, so scale by its devicePixelRatio. (-1, -1) = user cancelled."""
        if x < 0 or y < 0 or self._view is None:
            self.colorPicked.emit('')
            return
        try:
            pixmap = self._view.grab()
            dpr = pixmap.devicePixelRatio() or 1.0
            img = pixmap.toImage()
            px, py = int(x * dpr), int(y * dpr)
            if 0 <= px < img.width() and 0 <= py < img.height():
                self.colorPicked.emit(img.pixelColor(px, py).name())
            else:
                self.colorPicked.emit('')
        except Exception as e:
            print(f'[EYEDROPPER] in-page sample failed: {e}', flush=True)
            self.colorPicked.emit('')


class OdysseusPage(QWebEnginePage):
    """QWebEnginePage subclass that routes external links to the system browser."""

    def javaScriptConsoleMessage(self, level, message, line_number, source_id):
        # Chromium's --enable-logging=stderr captures the renderer's internal log but
        # NOT JavaScript console.log(); those only reach Python via this override.
        # Print without a prefix so structured [tag] messages sort cleanly in the log.
        label = level.name if hasattr(level, 'name') else str(level)
        if label in ('WARNING', 'ERROR', 'CRITICAL'):
            print(f'[JS:{label}] {message}', flush=True)
        else:
            print(message, flush=True)
        # When chatHistory.js evicts a Phase 2 batch, audit whether jsEventListeners
        # drops proportionally; confirms that WeakRef fixes released the closures.
        m = _RE_EVICT.match(message)
        if m:
            _cdp_executor.submit(_cdp_audit_listeners, int(m.group(1)))

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        if is_main_frame and url.host() not in ('localhost', '127.0.0.1'):
            QDesktopServices.openUrl(url)
            return False
        return super().acceptNavigationRequest(url, nav_type, is_main_frame)

    def createWindow(self, win_type):
        page = QWebEnginePage(self.profile(), self)
        page.urlChanged.connect(lambda url: (QDesktopServices.openUrl(url), page.deleteLater()))
        return page


class _InputIdleFilter(QObject):
    """App-level event filter that records the last user-input time and restarts the
    post-interaction idle timer.

    Qt WebEngine handles input internally, but Qt delivers these events at the
    QApplication level before Chromium consumes them, so installing this filter on
    QApplication.instance() catches all interaction over any widget or the web
    content area. It tracks keyboard as well as mouse so that typing defers the
    reclaim purge: a forcible purge causes a ~1s stutter, so it must never fire
    mid-typing.
    """
    _INPUT_EVENTS = frozenset((
        QEvent.Type.MouseMove,
        QEvent.Type.MouseButtonPress,
        QEvent.Type.KeyPress,
        QEvent.Type.Wheel,
    ))

    def __init__(self, on_input, timer: QTimer, parent=None):
        super().__init__(parent)
        self._on_input = on_input
        self._timer = timer

    def eventFilter(self, obj, event):
        if event.type() in self._INPUT_EVENTS:
            self._on_input()
            self._timer.start()
        return False


class _QuitFilter(QObject):
    """App-level event filter that flags a genuine quit before any window's
    closeEvent runs.

    macOS delivers ⌘Q, the application/Dock menu's Quit, and the quit Apple
    Event as a QEvent.Quit posted to the QApplication, which Qt then turns into
    closeAllWindows(). OdysseusWindow.closeEvent hides-and-vetoes by default (so
    the red button keeps the app in the Dock); on a real quit it must accept
    instead. Catching QEvent.Quit here — before the derived closeEvents — sets
    the window's _quitting flag so it accepts. We do not consume the event
    (return False): Qt still runs its normal termination.
    """
    def __init__(self, window, parent=None):
        super().__init__(parent)
        self._window = window

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Quit:
            print('[LIFECYCLE] _QuitFilter: QEvent.Quit -> arm quit', flush=True)
            self._window._quitting = True
        return False


class OdysseusWindow(QMainWindow):
    def __init__(self, profile: QWebEngineProfile):
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.browser = QWebEngineView()
        page = OdysseusPage(profile, self.browser)
        self._page = page  # held for lifecycle management in changeEvent
        # Allow JS clipboard WRITES (copy buttons). Off by default in
        # QtWebEngine, which makes navigator.clipboard.writeText and the
        # execCommand('copy') fallback both silently no-op. Deliberately NOT
        # enabling JavascriptCanPaste, which would let pages READ the
        # system clipboard.
        page.settings().setAttribute(
            QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, True)
        self._last_purge = 0.0  # monotonic ts of last forcible renderer purge
        self._last_input = time.monotonic()  # ts of last mouse/keyboard activity
        self._quitting = False  # set by the app-level Quit filter; see closeEvent

        # Inject synchronous flag so JS knows it's running inside the Qt wrapper
        flag_script = QWebEngineScript()
        flag_script.setSourceCode("window.__QT_WRAPPER__ = true;")
        flag_script.setName("qt-wrapper-flag")
        flag_script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        flag_script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        page.scripts().insert(flag_script)

        # Inject Qt's qwebchannel.js from Qt's internal resources
        _f = QFile(":/qtwebchannel/qwebchannel.js")
        _f.open(QIODevice.OpenModeFlag.ReadOnly)
        _qwc_js = bytes(_f.readAll()).decode()
        _f.close()
        qwc_script = QWebEngineScript()
        qwc_script.setSourceCode(_qwc_js)
        qwc_script.setName("qwebchannel.js")
        qwc_script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        qwc_script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        page.scripts().insert(qwc_script)

        # Native bridge, held as instance attrs to prevent GC
        self._bridge = NativeBridge(view=self.browser)
        self._channel = QWebChannel(page)
        self._channel.registerObject("bridge", self._bridge)
        page.setWebChannel(self._channel)

        # Renderer crash recovery: auto-reload on OOM or hard crash
        self._crash_times = []
        def _on_renderer_crash(status, exit_code):
            label = {0: 'Normal', 1: 'Abnormal', 2: 'Crashed', 3: 'Killed(OOM)'}.get(
                status.value, f'Unknown({status.value})')
            print(f'[RENDERER] {label} exit={exit_code} at {_time.strftime("%H:%M:%S")}',
                  flush=True)
            if status.value == 0:
                return
            now = _time.monotonic()
            self._crash_times = [t for t in self._crash_times if now - t < 10]
            if self._crash_times:
                print('[RENDERER] Crash loop, not reloading', flush=True)
                return
            self._crash_times.append(now)
            print('[RENDERER] Scheduling reload in 1s', flush=True)
            QTimer.singleShot(1000, lambda: self.browser.setUrl(
                QUrl(f"http://localhost:{PORT}")))
        page.renderProcessTerminated.connect(_on_renderer_crash)

        # Periodic renderer memory snapshot (every 30s).
        # Reads renderer + host memory via proc_pid_rusage (cheap, in-process, no
        # ps subprocess per sample) and dispatches ONE CDP DOMCounters read to the
        # executor so the GUI thread never blocks on the 9222 socket. When node
        # accumulation is high, the drain timer triggers reclaim so collection
        # doesn't wait for the next focus-loss.
        _last_peak: list[int] = [0]      # renderer lifetime-max footprint, high-water
        _last_host_rss: list[int] = [0]  # host-process resident, previous sample
        _node_threshold_pending: list = [False]  # set by executor, drained on main thread

        def _log_dom_counters():
            # Executor thread: CDP socket I/O + log only. The node-threshold GC is
            # handed back to the Qt main thread via the drained flag because
            # runJavaScript must not be called from a worker thread.
            counts = _cdp_call('Memory.getDOMCounters')
            if not counts:
                return
            nodes = counts.get('nodes', 0)
            listeners = counts.get('jsEventListeners', 0)
            # listeners/node ratio should be roughly constant (~3–5× for a
            # typical chat session). A rising ratio indicates a listener leak
            # either removeEventListener is being skipped or setInterval
            # closures are preventing GC of elements that still hold listeners.
            ratio = f'{listeners / nodes:.1f}' if nodes else 'n/a'
            print(
                f'[CDP] nodes={nodes} '
                f'documents={counts.get("documents")} '
                f'listeners={listeners} (listeners/node={ratio})',
                flush=True,
            )
            # Detached node accumulation above this threshold means Oilpan is not
            # keeping up.
            if nodes > 50_000:
                print(
                    f'[GC] node-count threshold ({nodes} > 50000)'
                    f', async JS GC',
                    flush=True,
                )
                _node_threshold_pending[0] = True

        def _log_renderer_memory():
            pid = page.renderProcessPid()
            if pid:
                rss_kb, footprint_kb, peak_kb = _mac_process_mem_kb(pid)
                if rss_kb:
                    print(f'[MEM] pid={pid} VmRSS:\t{rss_kb} kB '
                          f'(footprint={footprint_kb} kB)', flush=True)
                if peak_kb > _last_peak[0]:
                    _last_peak[0] = peak_kb
                    print(f'[MEM] pid={pid} VmPeak:\t{peak_kb} kB (new peak)',
                          flush=True)
            # Host-process memory. This (mac_wrapper.py) embeds Chromium's browser
            # process plus the in-process GPU thread and the in-process network/
            # tracing services, so it is the largest single consumer in the stack
            # and is NOT covered by the renderer-pid reading above. We track it to
            # answer whether that footprint is a fixed baseline or climbs with use
            # (issue #112). The per-sample delta makes growth visible.
            host_rss, _host_fp, _host_peak = _mac_process_mem_kb(os.getpid())
            if host_rss:
                delta = host_rss - _last_host_rss[0] if _last_host_rss[0] else 0
                _last_host_rss[0] = host_rss
                print(f'[MEM] host pid={os.getpid()} VmRSS: '
                      f'{host_rss} kB (delta={delta:+d} kB)', flush=True)
            # At most one CDP call per sample, off the GUI thread.
            _cdp_executor.submit(_log_dom_counters)
            # This periodic timer is telemetry only. The renderer purge is NOT
            # fired here: the timer runs regardless of interaction and a forcible
            # purge causes a ~1s stutter. Reclaim happens strictly off the
            # interaction path (mouse-idle and focus-loss) via _purge_renderer.
            # The previous call here, simulatePressureNotification('critical'), was
            # a no-op on QtWebEngine (measured: no RSS change); issue #106.

        self._mem_timer = QTimer()
        self._mem_timer.timeout.connect(_log_renderer_memory)
        self._mem_timer.start(30_000)
        _start_macos_memory_monitor()

        # Focus-loss GC timer: 500 ms single-shot debounce started on WindowDeactivate,
        # cancelled on WindowActivate.  Skips transient focus shifts (notifications,
        # dropdowns) that would otherwise trigger unnecessary GC mid-typing.
        def _on_focus_loss_gc():
            print('[GC] focus-loss: async JS GC', flush=True)
            page.runJavaScript(
                "if(typeof gc==='function')"
                "gc({type:'major',execution:'async'});"
            )
            # Window is not focused: a reclaim stutter is invisible. Gated and
            # rate-limited inside _purge_renderer.
            self._purge_renderer('focus-loss')
        self._gc_focus_timer = QTimer()
        self._gc_focus_timer.setSingleShot(True)
        self._gc_focus_timer.timeout.connect(_on_focus_loss_gc)

        # Drain timer: polls the cross-thread event cells every 250 ms on the main
        # thread. QTimer.singleShot from a daemon Python thread (the memorystatus
        # monitor) or an executor worker has no event loop to fire on; this polling
        # pattern is the correct cross-thread dispatch (same as qt_wrapper's PSI
        # drain). Two cells: the pressure level (monitor thread) and the
        # node-threshold flag (DOMCounters executor task).
        def _drain_events():
            level = _pressure_event_pending[0]
            if level is not None:
                _pressure_event_pending[0] = None
                if level >= _MACOS_PRESSURE_CRITICAL:
                    # Routed through the shared gate: the RSS ceiling and 15 s rate
                    # limit stop sustained pressure from purging on every wakeup.
                    action = self._purge_renderer('low-memory')
                else:
                    # Warning: non-disruptive async GC only; escalate to the
                    # blocking purge only at critical.
                    page.runJavaScript(
                        "if(typeof gc==='function')"
                        "gc({type:'major',execution:'async'});"
                    )
                    action = 'async-gc'
                print(
                    f'[MEM] macOS pressure level={level} action={action}',
                    flush=True,
                )
            if _node_threshold_pending[0]:
                _node_threshold_pending[0] = False
                page.runJavaScript(
                    "if(typeof gc==='function')"
                    "gc({type:'major',execution:'async'});"
                )
                self._purge_renderer('node-threshold')
        self._gc_drain_timer = QTimer()
        self._gc_drain_timer.timeout.connect(_drain_events)
        self._gc_drain_timer.start(250)

        # Post-interaction reclaim: when input has been still for 2 seconds the user
        # has paused, so a reclaim stutter is invisible. This gives a fast reclaim
        # right after the user stops, for the focused-but-idle case (reading a long
        # response) that focus-loss does not cover. Gated and rate-limited inside
        # _purge_renderer, so it only fires when memory is actually over budget.
        self._idle_evict_timer = QTimer(self)
        self._idle_evict_timer.setSingleShot(True)
        self._idle_evict_timer.setInterval(2000)

        def _evict_on_idle():
            self._purge_renderer('post-interaction-idle')

        self._idle_evict_timer.timeout.connect(_evict_on_idle)
        self._idle_filter = _InputIdleFilter(
            self._mark_input, self._idle_evict_timer, self)
        QApplication.instance().installEventFilter(self._idle_filter)

        # Sustained-idle reclaim: the post-interaction timer is single-shot and only
        # re-arms on input, so a user who walks away gets exactly one purge and then
        # the renderer climbs unbounded (it filled all RAM in testing). This repeating
        # timer fixes that: every few seconds, if there has been no input for
        # _IDLE_RECLAIM_AFTER_S, attempt a purge. _purge_renderer is gated by the RSS
        # ceiling and rate-limited, so an idle-but-present user sees a reclaim only
        # every few minutes (when RSS climbs back over the ceiling), never mid-input.
        self._idle_reclaim_timer = QTimer(self)
        self._idle_reclaim_timer.setInterval(4000)
        self._idle_reclaim_timer.timeout.connect(self._maybe_idle_purge)
        self._idle_reclaim_timer.start()

        # Renderer hang watchdog (issue #137). A deadlocked renderer main thread
        # (observed live: condition-wait inside the WebEngine core, zero JS
        # execution contexts, hover still painting via the GPU compositor) never
        # dies, so renderProcessTerminated stays silent and the app looks
        # "partially frozen" until the user kills it. Probe liveness with a
        # runJavaScript ping: its callback is serviced by the renderer main
        # thread, so a wedged main thread never answers. After enough
        # consecutive unanswered pings (thresholds in qt_watchdog), recover with
        # a browser-process-side CDP Page.reload — the same call that recovered
        # the live incident; it needs no cooperation from the wedged renderer.
        # If CDP itself fails, fall back to WebAction.Reload on the next tick
        # (main thread — triggerAction must not be called from the executor).
        self._hang_detector = qt_watchdog.HangDetector()
        self._hang_cdp_failed = [False]
        page.loadFinished.connect(
            lambda _ok: self._hang_detector.on_pong())

        def _hang_recover_cdp():
            res = _cdp_call('Page.reload')
            print(
                f'[HANG] CDP Page.reload {"ok" if res is not None else "FAILED"}',
                flush=True,
            )
            if res is None:
                self._hang_cdp_failed[0] = True

        def _hang_tick():
            if page.renderProcessPid() is None:
                # Renderer dead or respawning: the renderProcessTerminated
                # handler owns that path; judging silence here would double-fire.
                return
            if self._hang_cdp_failed[0]:
                self._hang_cdp_failed[0] = False
                print('[HANG] CDP reload failed, falling back to '
                      'WebAction.Reload', flush=True)
                page.triggerAction(QWebEnginePage.WebAction.Reload)
                return
            if self._hang_detector.should_recover():
                # Read the silence BEFORE record_recovery() — it resets the
                # pong clock, so reading it after always logs 0s.
                _silence = self._hang_detector.silence_s()
                self._hang_detector.record_recovery()
                print(
                    f'[HANG] renderer pid={page.renderProcessPid()} '
                    f'unresponsive {_silence:.0f}s '
                    f'({qt_watchdog.MIN_MISSED_PINGS}+ pings unanswered), '
                    f'forcing Page.reload', flush=True,
                )
                _cdp_executor.submit(_hang_recover_cdp)
                return
            self._hang_detector.on_ping_sent()
            page.runJavaScript('1', lambda _r: self._hang_detector.on_pong())

        self._hang_timer = QTimer(self)
        self._hang_timer.setInterval(int(qt_watchdog.PING_INTERVAL_S * 1000))
        self._hang_timer.timeout.connect(_hang_tick)
        self._hang_timer.start()

        self.browser.setPage(page)
        # Set compositor base-background-colour AFTER setPage() so it is not
        # discarded during page initialisation. Shows in any brief pre-paint
        # gap; must match --bg so there is no flash of a lighter base colour.
        page.setBackgroundColor(_theme_bg_color())
        self.browser.setUrl(QUrl(f"http://localhost:{PORT}"))
        self.setCentralWidget(self.browser)
        self.resize(1280, 800)
        self._build_menus()

    def _renderer_rss_kb(self) -> int:
        page = getattr(self, '_page', None)
        pid = page.renderProcessPid() if page else None
        if not pid:
            return 0
        return _mac_process_mem_kb(pid)[0]

    def _purge_renderer(self, reason: str) -> str:
        """Forcibly purge renderer caches: the multi-GB pool that
        simulatePressureNotification does not touch on QtWebEngine (issue #106).

        Called only where a ~1s stutter is invisible: post-interaction mouse-idle,
        sustained idle (no input for a few seconds), focus-loss, minimize, and the
        memorystatus critical-pressure event. Gated by an RSS ceiling so light use
        never pays the stutter, and rate-limited so it cannot repeat back to back.
        The purge runs in the CDP executor so the socket I/O is off the Qt main
        thread. Logs the reason and the RSS delta on each purge; gated skips are
        intentionally silent (the idle timer would otherwise spam the log every
        few seconds).

        Returns the synchronous *decision* ('skipped_ceiling' / 'rate_limited' /
        'submitted') so a caller can log which branch was taken; the realized
        ok/FAILED + RSS delta is the deferred [MEM] line emitted from _do(). Most
        callers ignore the return.
        """
        import time
        rss = self._renderer_rss_kb()
        if rss and rss < _PURGE_RSS_CEILING_KB:
            return 'skipped_ceiling'  # below ceiling, not worth the stutter
        now = time.monotonic()
        if now - self._last_purge < _PURGE_MIN_INTERVAL_S:
            return 'rate_limited'
        self._last_purge = now

        def _do():
            if reason not in _PURGE_PRESSURE_REASONS and _renderer_busy():
                print(f'[MEM] forcible purge ({reason}): skipped_busy '
                      f'(active download/serve — purging a busy renderer segfaults it)',
                      flush=True)
                return
            res = _cdp_call('Memory.forciblyPurgeJavaScriptMemory')
            after = self._renderer_rss_kb()
            print(
                f'[MEM] forcible purge ({reason}): '
                f'{"ok" if res is not None else "FAILED"} '
                f'RSS {rss} -> {after} kB (delta={rss - after:+d} kB)',
                flush=True,
            )
        _cdp_executor.submit(_do)
        return 'submitted'

    def _mark_input(self) -> None:
        """Record the time of the latest user input (mouse or keyboard)."""
        self._last_input = time.monotonic()

    def _maybe_idle_purge(self) -> None:
        """Repeating sustained-idle reclaim, the safety net for a user who stays in
        the (focused) window but walks away from the keyboard. Only fires after a
        genuine away-from-keyboard gap (_IDLE_RECLAIM_AFTER_S) so the ~1s blocking
        purge never lands on an interaction; the switched-away / minimized cases are
        reclaimed immediately by the focus-loss and minimize purges instead.
        _purge_renderer still adds the RSS-ceiling gate and rate limit."""
        if time.monotonic() - self._last_input >= _IDLE_RECLAIM_AFTER_S:
            self._purge_renderer('sustained-idle')

    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowStateChange:
            if self.isMinimized():
                # Reclaim renderer memory while minimized WITHOUT freezing the page.
                # The lifecycle freeze released compositor memory but left the web
                # content unresponsive to input after the Frozen->Active thaw; Qt
                # documents that a non-Active page can lose HTML input, says
                # "a visible page must remain in the Active state", and PyQt's
                # lifecycle transitions are unreliable (issue #109). The gated purge
                # frees memory without touching the lifecycle state; its ~1s stutter
                # is invisible while minimized.
                print('[LIFECYCLE] minimized: page kept Active, reclaim requested',
                      flush=True)
                self._purge_renderer('minimized')
        elif event.type() == QEvent.Type.WindowDeactivate:
            # Minimize fires both WindowStateChange and WindowDeactivate; only run
            # the focus-loss GC when actually losing focus (not minimizing).
            if not self.isMinimized():
                self._gc_focus_timer.start(500)
        elif event.type() == QEvent.Type.WindowActivate:
            self._gc_focus_timer.stop()
        super().changeEvent(event)

    def _save_window_state(self):
        s = QSettings("odysseus", "odysseus")
        s.setValue("windowMaximized", self.isMaximized())
        # Only write geometry when windowed: saveGeometry() while maximized would
        # record the maximized dimensions as the "normal" size and destroy the
        # restore target on next open. Skipping the write when maximized leaves
        # the last good windowed geometry intact in QSettings.
        if not self.isMaximized():
            s.setValue("windowGeometry", self.saveGeometry())
        s.sync()

    def request_quit(self):
        # Deterministic quit for ⌘Q and the application-menu Quit (see the Quit
        # QAction in _build_menus): set _quitting, then exit the event loop.
        # app.quit() does not route through closeEvent, so there is no veto to
        # dodge; teardown runs on app.aboutToQuit. This path does NOT depend on
        # the platform posting a QEvent.Quit — that dependency (for the Dock
        # menu's Quit and the quit Apple Event) is handled separately by
        # _QuitFilter, which sets the same flag if such an event does arrive.
        self._quitting = True
        QApplication.instance().quit()

    def closeEvent(self, event):
        # macOS convention: the red close button hides the window; the app stays
        # in the Dock and is re-shown on Dock-click / Cmd-Tab (_on_app_state_
        # changed). A real quit must instead accept — and an unconditional
        # ignore() here would VETO ⌘Q if Qt routed it through closeAllWindows()
        # → closeEvent. The _quitting flag distinguishes them: it is set by
        # request_quit (⌘Q / app-menu Quit) and by _QuitFilter (Dock Quit / quit
        # Apple Event, which arrive as QEvent.Quit). When set, accept and let
        # aboutToQuit tear down; otherwise hide.
        if self._quitting:
            print('[LIFECYCLE] closeEvent: quitting -> accept', flush=True)
            event.accept()
            return
        print('[LIFECYCLE] closeEvent: hide, keep app in Dock', flush=True)
        self._save_window_state()
        self.hide()
        event.ignore()

    def _build_menus(self):
        # QMainWindow.menuBar() with no parent becomes the global macOS menu bar.
        # A native Edit menu is required so the standard ⌘X/C/V/A/Z shortcuts
        # reach the web view: on macOS those keys route through the first-
        # responder/menu chain, not the widget directly (unlike Win/Linux, where
        # QtWebEngine consumes them itself — hence this menu is mac-only).
        WA = QWebEnginePage.WebAction
        edit = self.menuBar().addMenu("Edit")

        def _action(title, std_key, web_action):
            act = QAction(title, self)
            act.setShortcut(QKeySequence(std_key))
            # triggerPageAction routes to whatever currently has focus in the page
            # (any input, textarea, or contenteditable), matching native behavior.
            act.triggered.connect(
                lambda _checked=False, wa=web_action: self.browser.triggerPageAction(wa))
            edit.addAction(act)

        SK = QKeySequence.StandardKey
        _action("Undo", SK.Undo, WA.Undo)
        _action("Redo", SK.Redo, WA.Redo)
        edit.addSeparator()
        _action("Cut", SK.Cut, WA.Cut)
        _action("Copy", SK.Copy, WA.Copy)
        _action("Paste", SK.Paste, WA.Paste)
        edit.addSeparator()
        _action("Select All", SK.SelectAll, WA.SelectAll)

        # Explicit Quit so ⌘Q binds deterministically to request_quit rather
        # than depending on the platform delivering a QEvent.Quit. QuitRole
        # relocates this into the macOS application menu (the "Odysseus" menu),
        # replacing Qt's automatic Quit item — so it does not appear under Edit
        # and there is no duplicate/ambiguous ⌘Q. It must live in a menu for its
        # shortcut to be active, hence adding it here.
        quit_act = QAction("Quit Odysseus", self)
        quit_act.setShortcut(QKeySequence(SK.Quit))
        quit_act.setMenuRole(QAction.MenuRole.QuitRole)
        quit_act.triggered.connect(self.request_quit)
        edit.addAction(quit_act)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    app = QApplication(sys.argv)
    # macOS convention: closing the last window does NOT quit the app — it stays
    # in the Dock. OdysseusWindow.closeEvent hides instead of closing; the app
    # quits only via ⌘Q / the application menu's Quit (Qt's automatic items),
    # which exit the event loop and fire aboutToQuit for teardown below.
    app.setQuitOnLastWindowClosed(False)

    # Single-instance guard, BEFORE kill_zombies/start_server: a second launch
    # (double-clicked launcher, Dock click race) must focus the existing
    # window — the behavior users expect from a desktop app — not start a
    # rival wrapper whose kill_zombies would kill the first instance's server
    # out from under its window. QLocalServer is a Unix domain socket here
    # (named pipe on Windows); removeServer() clears a stale socket left by a
    # crashed previous instance, so a real second instance is detected only by
    # a live connect.
    _SINGLETON = "odysseus-desktop-wrapper"
    _probe = QLocalSocket()
    _probe.connectToServer(_SINGLETON)
    if _probe.waitForConnected(500):
        _probe.write(b"raise\n")
        _probe.waitForBytesWritten(500)
        _probe.disconnectFromServer()
        print("[SINGLETON] already running; focused the existing window instead")
        sys.exit(0)
    QLocalServer.removeServer(_SINGLETON)
    _singleton_server = QLocalServer()
    _singleton_server.listen(_SINGLETON)

    kill_zombies()
    start_server()
    # Dock tile. On macOS, setWindowIcon(QIcon) REPLACES the tile at runtime —
    # even for a bundled .app — so calling it inside a bundle made the icon
    # change the instant the app started (the bundle's .icns tile swapped for
    # this image). When launched from the bundle (ODYSSEUS_BUNDLE=1, set by the
    # launcher), leave the tile to the bundle's .icns so running looks identical
    # to not-running. For a bare `python mac_wrapper.py` dev run there is no
    # bundle icon, so set one — the macOS tile master, falling back to the bare
    # glyph — otherwise the Dock shows the generic Python rocket.
    if not os.environ.get("ODYSSEUS_BUNDLE"):
        for _name in ("icon-macos-1024.png", "icon-512.png"):
            _icon_path = os.path.join(INSTALL_DIR, "static", "icons", _name)
            if os.path.isfile(_icon_path):
                app.setWindowIcon(QIcon(_icon_path))
                break

    # Named persistent profile: cookies, localStorage, and session data
    # survive between restarts. Without this the login is lost on every close.
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)
    profile = QWebEngineProfile(PROFILE_NAME, None)
    profile.setPersistentStoragePath(DATA_DIR)
    profile.setCachePath(CACHE_DIR)
    profile.setPersistentCookiesPolicy(
        QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies
    )
    # App serves from localhost; HTTP cache is almost entirely idle but grows
    # without bound by default. Cap at 50 MB.
    profile.setHttpCacheMaximumSize(50_000_000)

    win = OdysseusWindow(profile)
    win.show()

    def _show_and_raise():
        # Bring the window to the foreground: un-minimize first, or raise_()
        # targets the minimized placeholder and nothing visible moves.
        if win.isMinimized():
            win.showNormal()
        win.show()
        win.raise_()
        win.activateWindow()

    def _raise_existing_window():
        # A second launch connected to the singleton pipe.
        conn = _singleton_server.nextPendingConnection()
        if conn is not None:
            conn.disconnectFromServer()
        _show_and_raise()
    _singleton_server.newConnection.connect(_raise_existing_window)

    def _on_app_state_changed(state):
        # macOS Dock-reopen: after the red button hides the window, clicking the
        # Dock icon (or Cmd-Tab back) re-activates the app; if the window is
        # hidden we re-show it — the standard "reopen" behavior. Idempotent and
        # safe when the window is already visible, so we don't depend on
        # identifying the one true reopen event.
        if state == Qt.ApplicationState.ApplicationActive and not win.isVisible():
            print('[LIFECYCLE] reopen: app activated with hidden window -> show', flush=True)
            _show_and_raise()
    app.applicationStateChanged.connect(_on_app_state_changed)

    def _teardown():
        # Single teardown path for every real quit (⌘Q, application-menu Quit,
        # app.quit()): persist window state and stop the embedded server, then
        # HARD-EXIT before Qt destroys the QWebEngineView.
        #
        # Why hard-exit: QtWebEngine 6.11 intermittently null-derefs in
        # QWebEnginePage::setVisible on the CrBrowserMain thread while Qt tears
        # the web view down at shutdown (the view's hideEvent calls setVisible on
        # a browser process that is already partly gone) — SIGSEGV
        # KERN_INVALID_ADDRESS at 0x10, surfaced as "Odysseus quit unexpectedly".
        # It happens AFTER all meaningful cleanup, so it is functionally harmless
        # but alarming. We've saved geometry and stopped the server here, and the
        # persistent profile flushes cookies/localStorage as they change, so
        # os._exit skips Qt's racy WebEngine teardown and the app quits cleanly.
        # aboutToQuit runs before widget destruction, so this pre-empts the crash.
        print('[LIFECYCLE] aboutToQuit teardown running', flush=True)
        win._save_window_state()
        stop_server()
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0)
    app.aboutToQuit.connect(_teardown)

    # _QuitFilter must be installed on the app AFTER the window exists: it arms
    # win._quitting on QEvent.Quit so closeEvent can tell a real quit from a
    # red-button hide. Held in a name so it is not garbage-collected.
    _quit_filter = _QuitFilter(win)
    app.installEventFilter(_quit_filter)

    # Restore window state from previous session. show() must precede any
    # geometry calls so the window handle exists. When opening maximized we skip
    # restoreGeometry() entirely: the stored geometry blob was saved while
    # windowed and is correct, but calling restoreGeometry() before
    # showMaximized() would make Qt treat the blob's size as the maximized size
    # rather than the restore target. We just maximize; Qt uses resize(1280,800)
    # from __init__ as the un-maximize restore target.
    _s = QSettings("odysseus", "odysseus")
    if _s.value("windowMaximized", False, type=bool):
        win.showMaximized()
    else:
        _geom = _s.value("windowGeometry")
        if _geom:
            win.restoreGeometry(_geom)

    sys.exit(app.exec())
