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

# GPU vendor detection. /proc/driver/nvidia is created by the NVIDIA proprietary
# kernel module (including nvidia-open); absent for Mesa drivers (AMD, Intel, Nouveau).
_is_nvidia = os.path.exists("/proc/driver/nvidia")

if _is_nvidia:
    # Qt 6.9+ regression: forces GBM even on drivers without GBM support.
    # NVIDIA proprietary does not implement GBM buffer allocation; the forced
    # path causes black windows (qutebrowser #8535). setdefault preserves any
    # user environment override.
    os.environ.setdefault("QTWEBENGINE_FORCE_USE_GBM", "0")

# DefaultANGLEVulkan omitted for all GPU types: forces ANGLE to a Vulkan
# backend, which conflicts with Qt WebEngine 6.6+'s own Vulkan path on
# ozone/Wayland and causes blank windows (Chromium bug 334275637).
_gpu_flags = []
if not _is_nvidia:
    # Mesa (AMD, Intel, Nouveau): GBM buffer allocation is the native rendering
    # path. Zero-copy avoids a CPU→GPU texture upload per rendered frame.
    # Omitted on NVIDIA proprietary: no GBM support in that driver.
    _gpu_flags.append("--enable-zero-copy")

os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join([
    "--no-sandbox",
    "--ignore-gpu-blocklist",
    "--enable-gpu-rasterization",
    "--enable-features=WebGPU,SharedArrayBuffer,PartitionAllocMemoryReclaimer,BlinkHeapCompaction",
    "--enable-logging=stderr --log-level=1",  # captured via os.dup2 into wrapper_system.log
    "--remote-debugging-port=9222",            # Chrome DevTools at http://localhost:9222
    "--js-flags=--expose-gc,--initial-old-space-size=128,--max-old-space-size=512,--optimize-for-size,--minor-mc",
    "--renderer-process-limit=1",
    "--disable-extensions",
    # NB: --enable-low-end-device-mode is deliberately NOT set. It caused a
    # lighter-rectangle raster tint on dark themes (its low-fidelity raster path,
    # tile-aligned, ~+4/+4/+5 lighter than --bg), and did not bound the actual
    # OOM, which is Oilpan detached-DOM growth (e.g. transient CSS :hover
    # pseudo-element churn), a separate pool from the raster tile budget.
    *_gpu_flags,
])

import concurrent.futures as _futures
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
from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage, QWebEngineScript
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage
from PyQt6.QtCore import QUrl, QObject, QFile, QIODevice, QTimer, QSettings, QEvent, pyqtSlot, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QColor

INSTALL_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_PYTHON = os.path.join(INSTALL_DIR, "venv", "bin", "python")
PORT = os.environ.get("APP_PORT", "7000")
WINDOW_TITLE = "Odysseus"
PROFILE_NAME = "odysseus"


def _theme_bg_color() -> QColor:
    """Read the saved theme background from data/user_prefs.json.

    setBackgroundColor() sets the QWebEnginePage compositor base-background
    colour — what shows in any brief gap before content paints. Hardcoding
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
DATA_DIR = os.path.expanduser("~/.local/share/odysseus/webengine")
CACHE_DIR = os.path.expanduser("~/.cache/odysseus/webengine")

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


def _cdp_browser_call(method, params=None):
    """One-shot CDP call on the browser target via stdlib WebSocket.

    Browser-level commands (e.g. Memory.simulatePressureNotification) must be sent
    to the browser target; they are not dispatched to renderer processes when called
    from a page target. The browser target URL is at /json/version rather than /json.
    Returns the CDP result dict or None on any error.
    """
    try:
        raw = _cdp_req.urlopen('http://localhost:9222/json/version', timeout=1).read()
        info = json.loads(raw)
        ws_url = info.get('webSocketDebuggerUrl')
        if not ws_url:
            return None
        return _cdp_ws_call(ws_url, method, params)
    except Exception:
        return None


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
# Pick the DEFAULT reclaim profile from device capability. LINUX-ONLY signals; this
# is the Linux wrapper; mac_wrapper.py / windows_wrapper.py carry their own platform
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

def _linux_total_ram_gb():
    try:
        with open('/proc/meminfo') as f:
            for line in f:
                if line.startswith('MemTotal:'):
                    return int(line.split()[1]) / (1024 * 1024)  # kB -> GB
    except (OSError, ValueError):
        pass
    return None

def _linux_software_render():
    """True when no hardware GPU render node exists (no /dev/dri/renderD*, or every
    card is bound only to the EFI framebuffer), so Chromium falls back to llvmpipe
    software raster, detected pre-launch from devfs/sysfs (the GPU-incident signal)."""
    import glob as _glob
    try:
        if not _glob.glob('/dev/dri/renderD*'):
            return True  # no render node => no GPU acceleration
        drivers = set()
        for drv in _glob.glob('/sys/class/drm/card*/device/driver'):
            try:
                drivers.add(os.path.basename(os.path.realpath(drv)))
            except OSError:
                pass
        return bool(drivers) and drivers <= {'simple-framebuffer', 'simpledrm'}
    except Exception:
        return False

_low_resource, _profile_reason = _classify_resources(_linux_total_ram_gb(), _linux_software_render())

# RSS ceiling: the renderer is only purged above this. Measured working set after a
# purge is ~430 MB, so the off-interaction reclaim sawtooth stays ~0.43 GB → ceiling.
# Default ~1.2 GB (a safety net; with producers eliminated the renderer rarely
# approaches it). Tunable via ODYSSEUS_PURGE_CEILING_MB: lower it on RAM-constrained
# machines for a tighter cap (purges fire sooner/more often, the right trade when
# system swap/OOM is worse than an occasional off-interaction stutter; this is the
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
# QtWebEngine (the only CDP reclaim is the synchronous OOM-intervention; Linux
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

# PSI pressure thresholds + the whole detection core live in qt_psi (a Qt-free module,
# so the logic is unit-testable without the GUI stack and mirrors the chromium project's
# detection-core/output-adapter split). This file is the output adapter: it drains
# qt_psi.psi_event_pending on the Qt main thread and turns each event into an action.
import qt_psi

# Log the selected profile once (diagnosable; notes when an env var overrode it).
_profile_overridden = bool(
    {'ODYSSEUS_IDLE_RECLAIM_S', 'ODYSSEUS_PURGE_CEILING_MB',
     'ODYSSEUS_PSI_MODERATE', 'ODYSSEUS_PSI_CRITICAL', 'ODYSSEUS_PSI_FULL_CRITICAL'}
    & os.environ.keys())
print(f"[PROFILE] {'low-resource' if _low_resource else 'standard'} ({_profile_reason}): "
      f"idle={_IDLE_RECLAIM_AFTER_S:.0f}s ceiling={_PURGE_RSS_CEILING_KB // 1024}MB "
      f"psi=some{qt_psi.PSI_MODERATE:.0f}/{qt_psi.PSI_CRITICAL:.0f}"
      f" full{qt_psi.PSI_FULL_CRITICAL:.0f}"
      f"{' [env override]' if _profile_overridden else ''}", flush=True)

def _cdp_audit_listeners(n_evicted: int) -> None:
    """Measure jsEventListeners delta 5 s after a Phase 2 eviction batch.

    Runs in a background thread. Captures the listener count immediately before
    sleeping (pre-GC baseline) then again after GC has had time to collect the
    evicted nodes. A delta close to zero after evicting N nodes with continue
    buttons indicates listener retention; a delta ≈ N confirms clean release.
    """
    pre = _cdp_call('Memory.getDOMCounters')
    pre_listeners = pre.get('jsEventListeners', 0) if pre else None
    _time.sleep(5)
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
    colorPicked = pyqtSignal(str)

    @pyqtSlot()
    def openColorPicker(self):
        bus = QDBusConnection.sessionBus()
        portal = QDBusInterface(
            'org.freedesktop.portal.Desktop',
            '/org/freedesktop/portal/desktop',
            'org.freedesktop.portal.Screenshot',
            bus,
        )
        if not portal.isValid():
            self._fallback()
            return

        reply = portal.call('PickColor', '', {})
        if reply.type() != QDBusMessage.MessageType.ReplyMessage:
            self._fallback()
            return

        request_path = str(reply.arguments()[0])
        bus.connect(
            'org.freedesktop.portal.Desktop',
            request_path,
            'org.freedesktop.portal.Request',
            'Response',
            self._on_response,
        )

    @pyqtSlot('uint', 'QVariantMap')
    def _on_response(self, response, results):
        QDBusConnection.sessionBus().disconnect(
            'org.freedesktop.portal.Desktop', '',
            'org.freedesktop.portal.Request', 'Response',
            self._on_response,
        )
        if response == 0 and 'color' in results:
            try:
                color = results['color']
                try:
                    r, g, b = color
                except TypeError:
                    color.beginStructure()
                    r, g, b = color.asVariant(), color.asVariant(), color.asVariant()
                    color.endStructure()
                self.colorPicked.emit('#{:02x}{:02x}{:02x}'.format(
                    round(r * 255), round(g * 255), round(b * 255)
                ))
                return
            except Exception as e:
                print(f'[BRIDGE] color portal error: {e}', flush=True)
        self.colorPicked.emit('')

    def _fallback(self):
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

        # Periodic renderer memory snapshot (every 60s).
        # Polls /proc/<pid>/status for RSS and CDP Memory.getDOMCounters for live
        # Oilpan node counts. When node accumulation is high, triggers a CDP purge
        # so collection doesn't wait for the next focus-loss event.
        _last_vmpeak: list[int] = [0]  # mutable cell for closure capture
        _last_host_rss: list[int] = [0]  # host-process RSS, previous sample

        def _log_renderer_memory():
            rss_before = 0
            pid = page.renderProcessPid()
            if pid:
                try:
                    with open(f'/proc/{pid}/status') as f:
                        for line in f:
                            if line.startswith('VmRSS'):
                                rss_before = int(line.split()[1])
                                print(f'[MEM] pid={pid} {line.rstrip()}', flush=True)
                            elif line.startswith('VmPeak'):
                                kb = int(line.split()[1])
                                if kb > _last_vmpeak[0]:
                                    _last_vmpeak[0] = kb
                                    print(f'[MEM] pid={pid} {line.rstrip()} (new peak)',
                                          flush=True)
                except OSError as e:
                    print(f'[MEM] error: {e}', flush=True)
            # Host-process RSS. This (qt_wrapper.py) embeds Chromium's browser
            # process plus the in-process GPU thread (Chrome_InProcGPUThread) and
            # the NetworkServiceInProcess2 / TracingServiceInProcess features, so
            # it is the largest single consumer in the stack and is NOT covered by
            # the renderer-pid reading above. We track it here to answer the open
            # question of whether that footprint is a fixed baseline or climbs with
            # use (issue #112). The per-sample delta makes growth visible directly.
            try:
                with open('/proc/self/status') as f:
                    for line in f:
                        if line.startswith('VmRSS'):
                            host_rss = int(line.split()[1])
                            delta = host_rss - _last_host_rss[0] if _last_host_rss[0] else 0
                            _last_host_rss[0] = host_rss
                            print(f'[MEM] host pid={os.getpid()} VmRSS: '
                                  f'{host_rss} kB (delta={delta:+d} kB)', flush=True)
                            break
            except OSError as e:
                print(f'[MEM] host error: {e}', flush=True)
            counts = _cdp_call('Memory.getDOMCounters')
            if counts:
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
                # keeping up.  Direct runJavaScript call is safe here because
                # _log_renderer_memory runs on the Qt main thread via QTimer.
                if nodes > 50_000:
                    print(
                        f'[GC] node-count threshold ({nodes} > 50000)'
                        f', async JS GC',
                        flush=True,
                    )
                    page.runJavaScript(
                        "if(typeof gc==='function')"
                        "gc({type:'major',execution:'async'});"
                    )
            # This periodic timer is telemetry only. The renderer purge is NOT
            # fired here: the timer runs regardless of interaction and a forcible
            # purge causes a ~1s stutter. Reclaim happens strictly off the
            # interaction path (mouse-idle and focus-loss) via _purge_renderer.
            # The previous call here, simulatePressureNotification('critical'), was
            # a no-op on QtWebEngine (measured: no RSS change); issue #106.
            del rss_before  # was only used by the removed eviction telemetry

        self._mem_timer = QTimer()
        self._mem_timer.timeout.connect(_log_renderer_memory)
        self._mem_timer.start(30_000)
        qt_psi.start_psi_monitor()

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

        # PSI drain timer: polls qt_psi.psi_event_pending every 250 ms on the main
        # thread. QTimer.singleShot from a daemon Python thread (the qt_psi monitor) has
        # no event loop to fire on; this polling pattern is the correct cross-thread
        # dispatch. The monitor (detection core) produced the level + metrics off-thread;
        # this adapter adds renderer RSS, dispatches the graduated action, and emits the
        # single greppable [PSI] line. The logged `action` is the synchronous *decision*
        # the realized purge result is the paired [MEM] forcible purge (psi-critical)
        # line, joined by the reason.
        def _drain_psi_events():
            event = qt_psi.psi_event_pending[0]
            if event is None:
                return
            qt_psi.psi_event_pending[0] = None
            action = qt_psi.dispatch_psi_action(
                event['requested'],
                on_async_gc=lambda: page.runJavaScript(
                    "if(typeof gc==='function')"
                    "gc({type:'major',execution:'async'});"
                ),
                on_critical=lambda: self._purge_renderer('psi-critical'),
            )
            rss_mb = self._renderer_rss_kb() // 1024
            avail = event['mem_avail_mb']
            swap = event['swap_mb']
            print(
                f"[PSI] level={event['level']} some={event['some']:.1f}"
                f" full={event['full']:.1f}"
                f" mem_avail_mb={avail if avail is not None else '?'}"
                f" rss_mb={rss_mb} swap_mb={swap if swap is not None else '?'}"
                f" action={action}",
                flush=True,
            )
        self._gc_drain_timer = QTimer()
        self._gc_drain_timer.timeout.connect(_drain_psi_events)
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
        try:
            with open(f'/proc/{pid}/status') as f:
                for line in f:
                    if line.startswith('VmRSS'):
                        return int(line.split()[1])
        except OSError:
            return 0
        return 0

    def _purge_renderer(self, reason: str) -> str:
        """Forcibly purge renderer caches: the multi-GB pool that
        simulatePressureNotification does not touch on QtWebEngine (issue #106).

        Called only where a ~1s stutter is invisible: post-interaction mouse-idle,
        sustained idle (no input for a few seconds), focus-loss, minimize, and PSI
        CRITICAL. Gated by an RSS ceiling so light use never pays the stutter, and
        rate-limited so it cannot repeat back to back. The purge runs in the CDP
        executor so the socket I/O is off the Qt main thread. Logs the reason and
        the RSS delta on each purge; gated skips are intentionally silent (the
        idle timer would otherwise spam the log every few seconds).

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
        # Only write geometry when windowed. On Wayland, saveGeometry() while
        # maximized records the maximized dimensions as the "normal" size, which
        # destroys the restore target on next open. Skipping the write when
        # maximized leaves the last good windowed geometry intact in QSettings.
        if not self.isMaximized():
            s.setValue("windowGeometry", self.saveGeometry())
        s.sync()
        self.browser.setPage(QWebEnginePage(QWebEngineProfile.defaultProfile(), self.browser))
        stop_server()
        event.accept()


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    kill_zombies()
    start_server()

    app = QApplication(sys.argv)
    # Tell KDE which .desktop file owns this window so it groups with the
    # pinned taskbar entry and shows the correct icon instead of the X logo.
    app.setDesktopFileName("odysseus")

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

    # Restore window state from previous session. show() must precede any
    # geometry calls so the window handle exists (required on Wayland).
    # When opening maximized we skip restoreGeometry() entirely: the stored
    # geometry blob was saved while windowed and is correct, but calling
    # restoreGeometry() before showMaximized() would make Qt treat the blob's
    # size as the maximized size rather than the restore target, repeating the
    # Wayland normal-geometry bug. We just maximize; Qt uses resize(1280,800)
    # from __init__ as the un-maximize restore target.
    _s = QSettings("odysseus", "odysseus")
    if _s.value("windowMaximized", False, type=bool):
        win.showMaximized()
    else:
        _geom = _s.value("windowGeometry")
        if _geom:
            win.restoreGeometry(_geom)

    sys.exit(app.exec())
