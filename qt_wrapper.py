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
os.dup2(_log_file.fileno(), 1)   # redirect fd 1: Chromium renderer stdout → our log
os.dup2(_log_file.fileno(), 2)   # redirect fd 2: Chromium renderer stderr → our log
sys.stdout = _log_file
sys.stderr = _log_file

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
    "--js-flags=--expose-gc --max-old-space-size=512",  # expose gc() + backstop heap cap
    *_gpu_flags,
])

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
from PyQt6.QtGui import QDesktopServices

INSTALL_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_PYTHON = os.path.join(INSTALL_DIR, "venv", "bin", "python")
PORT = os.environ.get("APP_PORT", "7000")
WINDOW_TITLE = "Odysseus"
PROFILE_NAME = "odysseus"
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
    cmd = [VENV_PYTHON, "-m", "uvicorn", "app:app",
           "--host", "127.0.0.1", "--port", PORT, "--access-log"]
    env = os.environ.copy()
    env["ODYSSEUS_LOG_FILE"] = os.path.join(LOG_DIR, "server.log")
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
    subprocess.run(["pkill", "-f", _UVICORN_PATTERN], check=False)
    print("Server stopped.")


def _signal_handler(sig, frame):
    stop_server()
    sys.exit(0)


def _cdp_call(method, params=None):
    """One-shot CDP call via stdlib WebSocket. Safe to call from any thread.

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


def _cdp_purge_memory():
    """Invoke V8/Oilpan major GC across all isolates via CDP.

    Memory.forciblyPurgeJavaScriptMemory calls V8::LowMemoryNotification() in the
    renderer process — no --expose-gc flag needed, works across all V8 isolates.
    Pure stdlib; safe to call from any background thread.
    """
    _cdp_call('Memory.forciblyPurgeJavaScriptMemory')
    print('[GC] CDP Memory.forciblyPurgeJavaScriptMemory dispatched', flush=True)


def _start_psi_monitor():
    """Background thread monitoring Linux /proc/pressure/memory (PSI).

    PSI avg10 measures the fraction of time tasks are stalled waiting for memory
    over the last 10 seconds. When it exceeds 5% the system is under genuine memory
    pressure. This mirrors the OS memory-pressure signal path that is absent in
    embedded QtWebEngine builds — the signal that would normally trigger Oilpan's
    automatic collection in a regular browser.

    Skipped silently on kernels < 4.20 and non-Linux platforms.
    """
    _PSI_PATH = '/proc/pressure/memory'
    _POLL_INTERVAL = 5    # seconds
    _THRESHOLD_PCT = 5.0  # avg10 % that triggers a purge

    if not os.path.exists(_PSI_PATH):
        return

    def _loop():
        while True:
            try:
                with open(_PSI_PATH) as f:
                    for line in f:
                        if line.startswith('some'):
                            avg10 = float(line.split()[1].split('=')[1])
                            if avg10 > _THRESHOLD_PCT:
                                print(
                                    f'[MEM] PSI avg10={avg10:.2f}% > {_THRESHOLD_PCT}%'
                                    f' — triggering CDP purge',
                                    flush=True,
                                )
                                _cdp_purge_memory()
                            break
            except Exception:
                pass
            _time.sleep(_POLL_INTERVAL)

    _threading.Thread(target=_loop, daemon=True, name='psi-monitor').start()
    print('[MEM] PSI memory pressure monitor started', flush=True)


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
                print(f'Color portal error: {e}')
        self.colorPicked.emit('')

    def _fallback(self):
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


class OdysseusWindow(QMainWindow):
    def __init__(self, profile: QWebEngineProfile):
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.browser = QWebEngineView()
        page = OdysseusPage(profile, self.browser)

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
        # Polls /proc/<pid>/status for RSS and CDP Memory.getDOMCounters for live
        # Oilpan node counts. When node accumulation is high, triggers a CDP purge
        # so collection doesn't wait for the next focus-loss event.
        def _log_renderer_memory():
            try:
                r = subprocess.run(
                    ['pgrep', '-f', 'QtWebEngineProcess'], capture_output=True, text=True)
                for pid_s in r.stdout.strip().split():
                    try:
                        with open(f'/proc/{pid_s}/status') as f:
                            for line in f:
                                if line.startswith(('VmRSS', 'VmPeak')):
                                    print(f'[MEM] pid={pid_s} {line.rstrip()}', flush=True)
                    except OSError:
                        pass
            except Exception as e:
                print(f'[MEM] error: {e}', flush=True)
            counts = _cdp_call('Memory.getDOMCounters')
            if counts:
                nodes = counts.get('nodes', 0)
                listeners = counts.get('jsEventListeners', 0)
                # listeners/node ratio should be roughly constant (~3–5× for a
                # typical chat session). A rising ratio indicates a listener leak
                # — either removeEventListener is being skipped or setInterval
                # closures are preventing GC of elements that still hold listeners.
                ratio = f'{listeners / nodes:.1f}' if nodes else 'n/a'
                print(
                    f'[CDP] nodes={nodes} '
                    f'documents={counts.get("documents")} '
                    f'listeners={listeners} (listeners/node={ratio})',
                    flush=True,
                )
                # Detached node accumulation above this threshold means Oilpan is not
                # keeping up. Purge proactively rather than waiting for focus-loss.
                if nodes > 50_000:
                    print(
                        f'[GC] node-count threshold ({nodes} > 50000)'
                        f' — triggering CDP purge',
                        flush=True,
                    )
                    _threading.Thread(
                        target=_cdp_purge_memory, daemon=True, name='threshold-gc',
                    ).start()

        self._mem_timer = QTimer()
        self._mem_timer.timeout.connect(_log_renderer_memory)
        self._mem_timer.start(60_000)
        _start_psi_monitor()

        self.browser.setPage(page)
        self.browser.setUrl(QUrl(f"http://localhost:{PORT}"))
        self.setCentralWidget(self.browser)
        self.resize(1280, 800)

    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowDeactivate:
            # Window lost focus — the compositor is not painting, so it is safe to
            # run GC now. Use CDP in a daemon thread so the Qt event loop is not
            # blocked by the WebSocket handshake; the renderer is idle anyway.
            _threading.Thread(
                target=_cdp_purge_memory, daemon=True, name='focus-loss-gc',
            ).start()
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

    # Named persistent profile — cookies, localStorage, and session data
    # survive between restarts. Without this the login is lost on every close.
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)
    profile = QWebEngineProfile(PROFILE_NAME, None)
    profile.setPersistentStoragePath(DATA_DIR)
    profile.setCachePath(CACHE_DIR)
    profile.setPersistentCookiesPolicy(
        QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies
    )

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
