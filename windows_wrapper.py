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
# renderer's inherited fds to the log file, the file cannot be swapped while
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
# Under pythonw.exe (the Start-menu/desktop shortcut launch) sys.stdout and
# sys.stderr are None and fds 1/2 are invalid — an unguarded .flush() here
# killed the process before this log existed, i.e. double-click did nothing.
if sys.stdout is not None:
    sys.stdout.flush()
if sys.stderr is not None:
    sys.stderr.flush()
try:
    os.dup2(_log_file.fileno(), 1)   # redirect fd 1: Chromium renderer stdout → our log
    os.dup2(_log_file.fileno(), 2)   # redirect fd 2: Chromium renderer stderr → our log
except OSError:
    # pythonw: no inheritable console fds to replace. Renderer subprocesses
    # get the log through the Popen(stdout=...) handles instead.
    pass
sys.stdout = _log_file
sys.stderr = _log_file
print(f'[LOG] wrapper_system.log opened at {_time.strftime("%Y-%m-%dT%H:%M:%S")}',
      flush=True)

# Windows: Qt WebEngine uses ANGLE (D3D11) by default. No GPU vendor detection
# needed — ANGLE handles the backend selection transparently, so none of the
# Linux wrapper's GBM/zero-copy/NVIDIA branching applies here.

def _windows_software_render() -> bool:
    """True when no hardware display adapter is active, so ANGLE falls back to
    WARP (software D3D). Probe: EnumDisplayDevicesW — every ACTIVE adapter being
    the driverless "Microsoft Basic Display Adapter"/"Microsoft Basic Render
    Driver" is the WARP signal. Microseconds, no WMI/subprocess. Conservative:
    any error, or any real adapter present, reads as hardware."""
    DISPLAY_DEVICE_ACTIVE = 0x1
    try:
        import ctypes as _ct
        import ctypes.wintypes as _wt
        class _DISPLAY_DEVICEW(_ct.Structure):
            _fields_ = [("cb", _wt.DWORD), ("DeviceName", _wt.WCHAR * 32),
                        ("DeviceString", _wt.WCHAR * 128), ("StateFlags", _wt.DWORD),
                        ("DeviceID", _wt.WCHAR * 128), ("DeviceKey", _wt.WCHAR * 128)]
        enum = _ct.windll.user32.EnumDisplayDevicesW
        dev = _DISPLAY_DEVICEW(); i = 0; active = []
        while True:
            dev.cb = _ct.sizeof(dev)
            if not enum(None, i, _ct.byref(dev), 0):
                break
            if dev.StateFlags & DISPLAY_DEVICE_ACTIVE:
                active.append(dev.DeviceString)
            i += 1
        return bool(active) and all(
            s.startswith("Microsoft Basic") for s in active)
    except Exception:
        return False

_software_render = _windows_software_render()

# Forcing GPU rasterization onto a software raster (WARP here, SwiftShader on
# the macOS bench where the flicker was diagnosed) makes rendering worse, and
# WebGPU on it is pointless feature surface — emit both only with real hardware.
_gpu_flags = [] if _software_render else [
    "--ignore-gpu-blocklist",
    "--enable-gpu-rasterization",
]
_features = "SharedArrayBuffer,PartitionAllocMemoryReclaimer,BlinkHeapCompaction"
if not _software_render:
    _features = "WebGPU," + _features

os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join([
    "--no-sandbox",
    *_gpu_flags,
    f"--enable-features={_features}",
    "--enable-logging=stderr --log-level=1",  # captured via os.dup2 into wrapper_system.log
    "--remote-debugging-port=9222",            # Chrome DevTools at http://localhost:9222
    "--js-flags=--expose-gc,--initial-old-space-size=128,--max-old-space-size=512,--optimize-for-size,--minor-mc",
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
import subprocess
import threading as _threading
import time
from PyQt6.QtWidgets import QApplication, QMainWindow, QColorDialog
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import (
    QWebEngineProfile, QWebEnginePage, QWebEngineScript, QWebEngineSettings,
)
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtCore import QUrl, QObject, QFile, QIODevice, QTimer, QSettings, QEvent, pyqtSlot, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QColor, QIcon
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

# Every subprocess this wrapper spawns must pass CREATE_NO_WINDOW: under
# pythonw there is no console to inherit, so console-subsystem children
# (powershell, python.exe) otherwise pop a visible console window over the app.
_NOWIN = subprocess.CREATE_NO_WINDOW

INSTALL_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_PYTHON = os.path.join(INSTALL_DIR, "venv", "Scripts", "python.exe")
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


# APPDATA for data (shared across user sessions); LOCALAPPDATA for cache (per-machine)
DATA_DIR = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")), "odysseus", "webengine")
CACHE_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA", os.environ.get("APPDATA", os.path.expanduser("~"))),
    "odysseus", "cache")

_UVICORN_PATTERN = "uvicorn app:app"
_server_proc = None


def _kill_uvicorn_cim() -> int:
    """Terminate any process whose command line matches the uvicorn pattern.

    Windows has no pkill; taskkill's /FI filters do not accept a COMMANDLINE
    key (the old `taskkill /FI "COMMANDLINE eq ..."` here matched nothing and
    silently killed no one), so query CIM through PowerShell instead — present
    on every supported Windows. wmic.exe was REMOVED in Windows 11 24H2
    (FileNotFoundError on launch), so it is not an option either. Returns the
    number of processes stopped (0 when no orphan existed).
    """
    ps = (
        f"(Get-CimInstance Win32_Process -Filter \"CommandLine LIKE '%{_UVICORN_PATTERN}%'\" | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; $_ } | "
        "Measure-Object).Count"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        check=False, capture_output=True, text=True, creationflags=_NOWIN,
    )
    try:
        return int(result.stdout.strip())
    except (ValueError, AttributeError):
        return 0


def kill_zombies():
    if _kill_uvicorn_cim() > 0:
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
        # CREATE_NEW_PROCESS_GROUP so Ctrl+C in the wrapper doesn't propagate to server.
        # CREATE_NO_WINDOW because under pythonw the wrapper has no console, so a
        # console-subsystem python.exe child would otherwise pop its own console window.
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | _NOWIN,
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
    # Belt-and-suspenders: also kill any orphaned server the handle missed.
    _kill_uvicorn_cim()
    print("Server stopped.")


def _signal_handler(sig, frame):
    stop_server()
    sys.exit(0)


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


# ── Windows memory reads (pure ctypes; NO tasklist subprocesses) ──────────────────
# tasklist is a console-subsystem child (window-flash risk under pythonw), costs a
# process spawn per sample, and needs locale-dependent CSV parsing. The kernel
# already exposes the same numbers: psapi GetProcessMemoryInfo gives WorkingSetSize
# (the RSS analogue) and PeakWorkingSetSize (the VmPeak analogue) per pid, and
# GlobalMemoryStatusEx gives system totals. All readable in-process via ctypes.

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


class _MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_uint32),
        ("dwMemoryLoad", ctypes.c_uint32),
        ("ullTotalPhys", ctypes.c_uint64),
        ("ullAvailPhys", ctypes.c_uint64),
        ("ullTotalPageFile", ctypes.c_uint64),
        ("ullAvailPageFile", ctypes.c_uint64),
        ("ullTotalVirtual", ctypes.c_uint64),
        ("ullAvailVirtual", ctypes.c_uint64),
        ("ullAvailExtendedVirtual", ctypes.c_uint64),
    ]


class _PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_uint32),
        ("PageFaultCount", ctypes.c_uint32),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def _global_memory_status():
    """GlobalMemoryStatusEx → _MEMORYSTATUSEX, or None on failure."""
    try:
        stat = _MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(stat)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            return stat
    except Exception:
        pass
    return None


_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def _win_process_mem_kb(pid):
    """(WorkingSetSize kB, PeakWorkingSetSize kB) for pid, or (0, 0) on failure.

    PROCESS_QUERY_LIMITED_INFORMATION is enough for GetProcessMemoryInfo and is
    grantable across the renderer sandbox boundary; the wider PROCESS_QUERY_
    INFORMATION | PROCESS_VM_READ would be refused for protected processes.
    """
    try:
        handle = ctypes.windll.kernel32.OpenProcess(
            _PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not handle:
            return (0, 0)
        try:
            pmc = _PROCESS_MEMORY_COUNTERS()
            pmc.cb = ctypes.sizeof(pmc)
            if ctypes.windll.psapi.GetProcessMemoryInfo(
                    handle, ctypes.byref(pmc), pmc.cb):
                return (pmc.WorkingSetSize // 1024, pmc.PeakWorkingSetSize // 1024)
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    except Exception:
        pass
    return (0, 0)


def _win_self_mem_kb():
    """(WorkingSetSize kB, PeakWorkingSetSize kB) for this process, or (0, 0).

    GetCurrentProcess() is the -1 pseudo-handle: no OpenProcess/CloseHandle
    needed, and it always has full query rights on itself.
    """
    try:
        pmc = _PROCESS_MEMORY_COUNTERS()
        pmc.cb = ctypes.sizeof(pmc)
        if ctypes.windll.psapi.GetProcessMemoryInfo(
                ctypes.windll.kernel32.GetCurrentProcess(),
                ctypes.byref(pmc), pmc.cb):
            return (pmc.WorkingSetSize // 1024, pmc.PeakWorkingSetSize // 1024)
    except Exception:
        pass
    return (0, 0)


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
# Pick the DEFAULT reclaim profile from device capability. WINDOWS-ONLY signals; this
# is the Windows wrapper; qt_wrapper.py / mac_wrapper.py carry their own platform
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

def _windows_total_ram_gb():
    stat = _global_memory_status()
    if stat is not None:
        return stat.ullTotalPhys / (1024 ** 3)
    return None

# Software-render detection: _windows_software_render() (EnumDisplayDevicesW, next
# to the Chromium flag block — it must run before the flags are assembled).
_low_resource, _profile_reason = _classify_resources(_windows_total_ram_gb(), _software_render)

# RSS ceiling: the renderer is only purged above this. Measured working set after a
# purge is ~430 MB, so the off-interaction reclaim sawtooth stays ~0.43 GB → ceiling.
# Default ~1.2 GB (a safety net; with producers eliminated the renderer rarely
# approaches it). Tunable via ODYSSEUS_PURGE_CEILING_MB: lower it on RAM-constrained
# machines for a tighter cap (purges fire sooner/more often, the right trade when
# system paging is worse than an occasional off-interaction stutter; this is the
# "adaptive loading" response to a low-resource device; see docs/fork/
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
# imported here: PSI is a Linux kernel interface; the Windows pressure signal
# is CreateMemoryResourceNotification below.)
import qt_watchdog

# Log the selected profile once (diagnosable; notes when an env var overrode it).
_profile_overridden = bool(
    {'ODYSSEUS_IDLE_RECLAIM_S', 'ODYSSEUS_PURGE_CEILING_MB'} & os.environ.keys())
print(f"[PROFILE] {'low-resource' if _low_resource else 'standard'} ({_profile_reason}): "
      f"idle={_IDLE_RECLAIM_AFTER_S:.0f}s ceiling={_PURGE_RSS_CEILING_KB // 1024}MB"
      f"{' [env override]' if _profile_overridden else ''}", flush=True)

# Low-memory event cell, written by the kernel32 monitor thread and drained on the
# Qt main thread by the 250 ms drain timer (the same cross-thread dispatch pattern
# qt_wrapper.py uses for PSI events: QTimer.singleShot from a daemon thread has no
# event loop to fire on, so a polled cell is the correct hand-off). Single-element
# list assignment is GIL-atomic so no lock is needed. Holds available MB (int) or
# None when no event is pending.
_lowmem_event_pending: list = [None]


def _start_windows_memory_monitor():
    """Background thread watching Windows memory pressure via kernel32.

    CreateMemoryResourceNotification(LowMemoryResourceNotification) returns a
    kernel event handle that signals when the system's available memory falls
    below a platform-defined threshold. This is the Windows equivalent of the
    OS memory-pressure signal that Chromium's browser process receives in a
    normal installation but that does not reach the renderer sandbox in embedded
    QtWebEngine builds.

    WaitForSingleObject with a 30-second timeout re-checks the handle state
    periodically and avoids blocking indefinitely in case of handle issues.
    The thread only records the event (with available MB from
    GlobalMemoryStatusEx) into _lowmem_event_pending; the Qt-side drain timer
    routes it through the shared _purge_renderer gate, so sustained pressure
    cannot repeat-purge every wakeup — the RSS ceiling and rate limit apply
    exactly as they do to every other reclaim trigger.
    """
    _LOW_MEMORY = 0   # LowMemoryResourceNotification
    _WAIT_OBJECT_0 = 0
    _TIMEOUT_MS = 30_000

    def _loop():
        try:
            handle = ctypes.windll.kernel32.CreateMemoryResourceNotification(_LOW_MEMORY)
            if not handle:
                print('[MEM] Windows: CreateMemoryResourceNotification failed', flush=True)
                return
            print('[MEM] Windows memory pressure monitor active', flush=True)
            try:
                while True:
                    result = ctypes.windll.kernel32.WaitForSingleObject(
                        handle, _TIMEOUT_MS)
                    if result == _WAIT_OBJECT_0:
                        stat = _global_memory_status()
                        avail_mb = (stat.ullAvailPhys // (1024 * 1024)
                                    if stat is not None else -1)
                        _lowmem_event_pending[0] = avail_mb
                        # Back off a full wait period after signalling: the handle
                        # stays signaled while pressure persists, and the purge
                        # decision (gated) already happened on the Qt side.
                        _time.sleep(_TIMEOUT_MS / 1000)
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
        except Exception as e:
            print(f'[MEM] Windows memory monitor error: {e}', flush=True)

    _threading.Thread(target=_loop, daemon=True, name='win-mem-monitor').start()


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

    On Windows, QColorDialog.getColor() delegates to the Windows color-picker
    dialog. No DBus/XDG portal needed.
    """
    colorPicked = pyqtSignal(str)

    @pyqtSlot()
    def openColorPicker(self):
        color = QColorDialog.getColor()
        self.colorPicked.emit(color.name() if color.isValid() else '')


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
        self._bridge = NativeBridge()
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
        # Reads renderer + host working sets via ctypes (cheap, in-process, no
        # console-subsystem child to flash a window under pythonw) and dispatches
        # ONE CDP DOMCounters read to the executor so the GUI thread never blocks
        # on the 9222 socket. When node accumulation is high, the drain timer
        # triggers reclaim so collection doesn't wait for the next focus-loss.
        _last_peak: list[int] = [0]      # renderer PeakWorkingSetSize, high-water
        _last_host_rss: list[int] = [0]  # host-process working set, previous sample
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
                rss_kb, peak_kb = _win_process_mem_kb(pid)
                if rss_kb:
                    print(f'[MEM] pid={pid} VmRSS:\t{rss_kb} kB', flush=True)
                if peak_kb > _last_peak[0]:
                    _last_peak[0] = peak_kb
                    print(f'[MEM] pid={pid} VmPeak:\t{peak_kb} kB (new peak)',
                          flush=True)
            # Host-process working set. This (windows_wrapper.py) embeds Chromium's
            # browser process plus the in-process GPU thread and the in-process
            # network/tracing services, so it is the largest single consumer in the
            # stack and is NOT covered by the renderer-pid reading above. We track
            # it to answer whether that footprint is a fixed baseline or climbs
            # with use (issue #112). The per-sample delta makes growth visible.
            host_rss, _host_peak = _win_self_mem_kb()
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
        _start_windows_memory_monitor()

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
        # thread. QTimer.singleShot from a daemon Python thread (the kernel32
        # monitor) or an executor worker has no event loop to fire on; this polling
        # pattern is the correct cross-thread dispatch (same as qt_wrapper's PSI
        # drain). Two cells: the low-memory notification (kernel32 thread) and the
        # node-threshold flag (DOMCounters executor task).
        def _drain_events():
            avail_mb = _lowmem_event_pending[0]
            if avail_mb is not None:
                _lowmem_event_pending[0] = None
                # Routed through the shared gate: the RSS ceiling and 15 s rate
                # limit stop sustained pressure from purging on every wakeup.
                action = self._purge_renderer('low-memory')
                print(
                    f'[MEM] Windows low-memory notification'
                    f' mem_avail_mb={avail_mb} action={action}',
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

    def _renderer_rss_kb(self) -> int:
        page = getattr(self, '_page', None)
        pid = page.renderProcessPid() if page else None
        if not pid:
            return 0
        return _win_process_mem_kb(pid)[0]

    def _purge_renderer(self, reason: str) -> str:
        """Forcibly purge renderer caches: the multi-GB pool that
        simulatePressureNotification does not touch on QtWebEngine (issue #106).

        Called only where a ~1s stutter is invisible: post-interaction mouse-idle,
        sustained idle (no input for a few seconds), focus-loss, minimize, and the
        kernel32 low-memory notification. Gated by an RSS ceiling so light use never
        pays the stutter, and rate-limited so it cannot repeat back to back. The
        purge runs in the CDP executor so the socket I/O is off the Qt main thread.
        Logs the reason and the RSS delta on each purge; gated skips are
        intentionally silent (the idle timer would otherwise spam the log every few
        seconds).

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

    def closeEvent(self, event):
        s = QSettings("odysseus", "odysseus")
        s.setValue("windowMaximized", self.isMaximized())
        # Only write geometry when windowed: saveGeometry() while maximized would
        # record the maximized dimensions as the "normal" size and destroy the
        # restore target on next open. Skipping the write when maximized leaves
        # the last good windowed geometry intact in QSettings.
        if not self.isMaximized():
            s.setValue("windowGeometry", self.saveGeometry())
        s.sync()
        self.browser.setPage(QWebEnginePage(QWebEngineProfile.defaultProfile(), self.browser))
        stop_server()
        event.accept()


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    # Without an explicit AppUserModelID, Windows groups the window under
    # pythonw.exe on the taskbar and shows the generic Python icon there
    # regardless of any Qt window icon. Must match the AppUserModelID stamped
    # on the shortcuts (build-windows-app.ps1), or the pinned icon and the
    # running window appear as two separate taskbar buttons.
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Odysseus.Odysseus")

    app = QApplication(sys.argv)

    # Single-instance guard, BEFORE kill_zombies/start_server: a second launch
    # (double-clicked shortcut, pinned icon while already running) must focus
    # the existing window — the behavior users expect from a desktop app — not
    # start a rival wrapper whose kill_zombies would murder the first
    # instance's server. QLocalServer.removeServer() clears a stale pipe left
    # by a crashed previous instance, so a real second instance is detected
    # only by a live connect.
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
    _icon_path = os.path.join(INSTALL_DIR, "static", "icon.ico")
    if os.path.isfile(_icon_path):
        app.setWindowIcon(QIcon(_icon_path))

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

    def _raise_existing_window():
        # A second launch connected to the singleton pipe: bring this window
        # to the foreground the way the shell would (un-minimize first, or
        # raise_() targets the minimized placeholder and nothing visible moves).
        conn = _singleton_server.nextPendingConnection()
        if conn is not None:
            conn.disconnectFromServer()
        if win.isMinimized():
            win.showNormal()
        win.show()
        win.raise_()
        win.activateWindow()
    _singleton_server.newConnection.connect(_raise_existing_window)

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
