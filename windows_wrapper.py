import json
import os
import sys
import time as _time

# ==============================================================================
# CRITICAL: Logging setup must happen BEFORE any PyQt6/QtWebEngine imports.
#
# sys.stdout/stderr alone is not enough — Chromium renderer subprocesses inherit
# OS-level file descriptors (fd 1, fd 2), not Python's sys.stdout/stderr.
# os.dup2 replaces the OS fds so all child process output lands in our log.
# ==============================================================================
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

_log_file = open(os.path.join(LOG_DIR, "wrapper_system.log"), "a", buffering=1)
sys.stdout.flush()
sys.stderr.flush()
os.dup2(_log_file.fileno(), 1)
os.dup2(_log_file.fileno(), 2)
sys.stdout = _log_file
sys.stderr = _log_file

# Windows: Qt WebEngine uses ANGLE (D3D11) by default. No GPU vendor detection
# needed — ANGLE handles the backend selection transparently.
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join([
    "--no-sandbox",
    "--ignore-gpu-blocklist",
    "--enable-gpu-rasterization",
    "--enable-features=WebGPU,SharedArrayBuffer,PartitionAllocMemoryReclaimer,BlinkHeapCompaction",
    "--enable-logging=stderr --log-level=1",
    "--remote-debugging-port=9222",
    "--js-flags=--expose-gc,--max-old-space-size=512",
    # NB: low-end-device-mode (the Chromium flag) is deliberately NOT set. It
    # caused a lighter-rectangle raster tint on dark themes and did not bound the
    # actual OOM — Oilpan detached-DOM churn, a separate pool from the raster
    # tile budget. See jdmanring/odysseus#96.
])

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
from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage, QWebEngineScript
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtCore import QUrl, QObject, QFile, QIODevice, QTimer, QSettings, QEvent, pyqtSlot, pyqtSignal
from PyQt6.QtGui import QDesktopServices

INSTALL_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_PYTHON = os.path.join(INSTALL_DIR, "venv", "Scripts", "python.exe")
PORT = os.environ.get("APP_PORT", "7000")
WINDOW_TITLE = "Odysseus"
PROFILE_NAME = "odysseus"
# APPDATA for data (shared across user sessions); LOCALAPPDATA for cache (per-machine)
DATA_DIR = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")), "odysseus", "webengine")
CACHE_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA", os.environ.get("APPDATA", os.path.expanduser("~"))),
    "odysseus", "cache")

_UVICORN_PATTERN = "uvicorn app:app"
_server_proc = None


def kill_zombies():
    # Windows has no pkill; terminate any orphaned uvicorn by WMI query.
    # Failure is expected when no orphan exists — suppress output.
    subprocess.run(
        ['wmic', 'process', 'where',
         f'commandline like "%{_UVICORN_PATTERN}%"', 'delete'],
        check=False, capture_output=True,
    )
    time.sleep(0.5)


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
    _access_log = open(os.path.join(LOG_DIR, "server_access.log"), "a", buffering=1)
    _server_proc = subprocess.Popen(
        cmd,
        cwd=INSTALL_DIR,
        env=env,
        stdout=_access_log,
        stderr=_access_log,
        # CREATE_NEW_PROCESS_GROUP so Ctrl+C in the wrapper doesn't propagate to server
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
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
    # Belt-and-suspenders: also kill any orphaned process via taskkill.
    subprocess.run(
        ['taskkill', '/F', '/FI', f'COMMANDLINE eq *{_UVICORN_PATTERN}*'],
        check=False, capture_output=True,
    )
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
    to the browser target — they are not dispatched to renderer processes when called
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


def _cdp_purge_memory():
    """Invoke V8/Oilpan major GC across all isolates via CDP.

    Memory.forciblyPurgeJavaScriptMemory calls V8::LowMemoryNotification() in the
    renderer process — no --expose-gc flag needed, works across all V8 isolates.
    Pure stdlib; safe to call from any background thread.
    """
    _cdp_call('Memory.forciblyPurgeJavaScriptMemory')
    print('[GC] CDP Memory.forciblyPurgeJavaScriptMemory dispatched', flush=True)


def _start_windows_memory_monitor():
    """Background thread monitoring Windows memory pressure via kernel32.

    CreateMemoryResourceNotification(LowMemoryResourceNotification) returns a
    kernel event handle that signals when the system's available memory falls
    below a platform-defined threshold. This is the Windows equivalent of the
    OS memory-pressure signal that Chromium's browser process receives in a
    normal installation but that does not reach the renderer sandbox in embedded
    QtWebEngine builds.

    WaitForSingleObject with a 30-second timeout re-checks the handle state
    periodically and avoids blocking indefinitely in case of handle issues.
    """
    _LOW_MEMORY = 0   # LowMemoryResourceNotification
    _WAIT_OBJECT_0 = 0
    _TIMEOUT_MS = 30_000
    _COOLDOWN_S = 10  # minimum seconds between consecutive purges

    def _loop():
        try:
            handle = ctypes.windll.kernel32.CreateMemoryResourceNotification(_LOW_MEMORY)
            if not handle:
                print('[MEM] Windows: CreateMemoryResourceNotification failed', flush=True)
                return
            print('[MEM] Windows memory pressure monitor active', flush=True)
            last_purge = 0.0
            try:
                while True:
                    result = ctypes.windll.kernel32.WaitForSingleObject(
                        handle, _TIMEOUT_MS)
                    if result == _WAIT_OBJECT_0:
                        now = _time.monotonic()
                        if now - last_purge >= _COOLDOWN_S:
                            print(
                                '[MEM] Windows low-memory notification'
                                ' — triggering CDP purge',
                                flush=True,
                            )
                            _cdp_purge_memory()
                            last_purge = now
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
        except Exception as e:
            print(f'[MEM] Windows memory monitor error: {e}', flush=True)

    _threading.Thread(target=_loop, daemon=True, name='win-mem-monitor').start()


class NativeBridge(QObject):
    """Python-to-JS bridge exposed via QWebChannel.

    On Windows, QColorDialog.getColor() delegates to the Windows color-picker
    dialog. No DBus portal needed.
    """
    colorPicked = pyqtSignal(str)

    @pyqtSlot()
    def openColorPicker(self):
        color = QColorDialog.getColor()
        self.colorPicked.emit(color.name() if color.isValid() else '')


class OdysseusPage(QWebEnginePage):
    """QWebEnginePage subclass that routes external links to the system browser."""

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        if is_main_frame and url.host() not in ('localhost', '127.0.0.1'):
            QDesktopServices.openUrl(url)
            return False
        return super().acceptNavigationRequest(url, nav_type, is_main_frame)

    def createWindow(self, win_type):
        page = QWebEnginePage(self.profile(), self)
        page.urlChanged.connect(lambda url: (QDesktopServices.openUrl(url), page.deleteLater()))
        return page


class _MouseIdleFilter(QObject):
    """App-level event filter that restarts a single-shot idle timer on every mouse move."""
    def __init__(self, timer: QTimer, parent=None):
        super().__init__(parent)
        self._timer = timer

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseMove:
            self._timer.start()
        return False


class OdysseusWindow(QMainWindow):
    def __init__(self, profile: QWebEngineProfile):
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.browser = QWebEngineView()
        page = OdysseusPage(profile, self.browser)
        self._page = page  # held for lifecycle management in changeEvent

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

        # Native bridge — held as instance attrs to prevent GC
        self._bridge = NativeBridge()
        self._channel = QWebChannel(page)
        self._channel.registerObject("bridge", self._bridge)
        page.setWebChannel(self._channel)

        # Renderer crash recovery — auto-reload on OOM or hard crash
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
                print('[RENDERER] Crash loop — not reloading', flush=True)
                return
            self._crash_times.append(now)
            print('[RENDERER] Scheduling reload in 1s', flush=True)
            QTimer.singleShot(1000, lambda: self.browser.setUrl(
                QUrl(f"http://localhost:{PORT}")))
        page.renderProcessTerminated.connect(_on_renderer_crash)

        # Periodic renderer memory snapshot (every 60s).
        # Polls tasklist for RSS and CDP Memory.getDOMCounters for Oilpan node counts.
        # Triggers a proactive CDP purge when node count exceeds threshold.
        def _rss_from_tasklist():
            total = 0
            try:
                r = subprocess.run(
                    ['tasklist', '/FI', 'IMAGENAME eq QtWebEngineProcess.exe',
                     '/FO', 'CSV', '/NH'],
                    capture_output=True, text=True)
                for line in r.stdout.strip().split('\n'):
                    if 'QtWebEngineProcess' in line:
                        parts = [p.strip('"') for p in line.split('","')]
                        if len(parts) >= 5:
                            try:
                                mem_kb = int(
                                    parts[4].replace('\xa0', '')
                                             .replace(',', '')
                                             .replace(' K', ''))
                                total += mem_kb
                            except ValueError:
                                pass
            except Exception:
                pass
            return total

        def _log_renderer_memory():
            try:
                r = subprocess.run(
                    ['tasklist', '/FI', 'IMAGENAME eq QtWebEngineProcess.exe',
                     '/FO', 'CSV', '/NH'],
                    capture_output=True, text=True)
                for line in r.stdout.strip().split('\n'):
                    if 'QtWebEngineProcess' in line:
                        parts = [p.strip('"') for p in line.split('","')]
                        if len(parts) >= 5:
                            pid = parts[1]
                            mem_kb = parts[4].replace('\xa0', '').replace(',', '').replace(' K', '')
                            print(f'[MEM] pid={pid} VmRSS:\t{mem_kb} kB', flush=True)
            except Exception as e:
                print(f'[MEM] error: {e}', flush=True)
            rss_before = _rss_from_tasklist()
            counts = _cdp_call('Memory.getDOMCounters')
            if counts:
                nodes = counts.get('nodes', 0)
                listeners = counts.get('jsEventListeners', 0)
                ratio = f'{listeners / nodes:.1f}' if nodes else 'n/a'
                print(
                    f'[CDP] nodes={nodes} '
                    f'documents={counts.get("documents")} '
                    f'listeners={listeners} (listeners/node={ratio})',
                    flush=True,
                )
                if nodes > 50_000:
                    print(
                        f'[GC] node-count threshold ({nodes} > 50000)'
                        f' — triggering CDP purge',
                        flush=True,
                    )
                    _threading.Thread(
                        target=_cdp_purge_memory, daemon=True, name='threshold-gc',
                    ).start()
            # critical pressure: cc::TileManager evicts everything not actively
            # composited, including all stale hover-state tiles from past interaction.
            result = _cdp_browser_call(
                'Memory.simulatePressureNotification', {'level': 'critical'}
            )
            print(
                f'[MEM] critical tile eviction: {"ok" if result is not None else "FAILED"}',
                flush=True,
            )
            # Telemetry: measure actual RSS freed by the eviction call.
            if rss_before:
                rss_after = _rss_from_tasklist()
                delta = rss_before - rss_after
                print(
                    f'[MEM] RSS after eviction: {rss_after} kB'
                    f' (delta={delta:+d} kB)',
                    flush=True,
                )

        self._mem_timer = QTimer()
        self._mem_timer.timeout.connect(_log_renderer_memory)
        self._mem_timer.start(30_000)
        _start_windows_memory_monitor()

        self._idle_evict_timer = QTimer(self)
        self._idle_evict_timer.setSingleShot(True)
        self._idle_evict_timer.setInterval(2000)

        def _evict_on_idle():
            def _do():
                result = _cdp_browser_call(
                    'Memory.simulatePressureNotification', {'level': 'critical'}
                )
                print(
                    f'[MEM] critical tile eviction (idle): '
                    f'{"ok" if result is not None else "FAILED"}',
                    flush=True,
                )
            _cdp_executor.submit(_do)

        self._idle_evict_timer.timeout.connect(_evict_on_idle)
        self._idle_filter = _MouseIdleFilter(self._idle_evict_timer, self)
        QApplication.instance().installEventFilter(self._idle_filter)

        self.browser.setPage(page)
        self.browser.setUrl(QUrl(f"http://localhost:{PORT}"))
        self.setCentralWidget(self.browser)
        self.resize(1280, 800)

    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowStateChange:
            if self.isMinimized():
                # Freeze halts rendering and releases compositor tile memory.
                # Risk: active SSE streams pause during freeze — acceptable for
                # short minimizes; the stream resumes when the page is thawed.
                self._page.setLifecycleState(QWebEnginePage.LifecycleState.Frozen)
                print('[LIFECYCLE] page frozen (minimized)', flush=True)
            else:
                self._page.setLifecycleState(QWebEnginePage.LifecycleState.Active)
                print('[LIFECYCLE] page active (restored)', flush=True)
        elif event.type() == QEvent.Type.WindowDeactivate:
            # Minimize fires both WindowStateChange and WindowDeactivate; skip the
            # GC call here to avoid running CDP on a frozen page.
            if not self.isMinimized():
                _threading.Thread(
                    target=_cdp_purge_memory, daemon=True, name='focus-loss-gc',
                ).start()
        super().changeEvent(event)

    def closeEvent(self, event):
        s = QSettings("odysseus", "odysseus")
        s.setValue("windowMaximized", self.isMaximized())
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

    # Named persistent profile — cookies, localStorage, and session data
    # survive between restarts.
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)
    profile = QWebEngineProfile(PROFILE_NAME, None)
    profile.setPersistentStoragePath(DATA_DIR)
    profile.setCachePath(CACHE_DIR)
    profile.setPersistentCookiesPolicy(
        QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies
    )
    # App serves from localhost — HTTP cache is almost entirely idle but grows
    # without bound by default. Cap at 50 MB.
    profile.setHttpCacheMaximumSize(50_000_000)

    win = OdysseusWindow(profile)
    win.show()

    _s = QSettings("odysseus", "odysseus")
    if _s.value("windowMaximized", False, type=bool):
        win.showMaximized()
    else:
        _geom = _s.value("windowGeometry")
        if _geom:
            win.restoreGeometry(_geom)

    sys.exit(app.exec())
