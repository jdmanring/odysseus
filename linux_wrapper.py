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

# Qt 6.9+ regression: QTWEBENGINE_FORCE_USE_GBM can cause black windows on NVIDIA.
# Set to "0" to disable. setdefault preserves any override from the environment.
os.environ.setdefault("QTWEBENGINE_FORCE_USE_GBM", "0")

os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
    "--no-sandbox "
    "--ignore-gpu-blocklist "
    "--enable-gpu-rasterization "
    # DefaultANGLEVulkan: forces ANGLE to use a Vulkan backend. Explicitly disallowed
    # on ozone/Wayland (Chromium bug 334275637) — causes blank windows on NVIDIA/Wayland.
    # Qt WebEngine 6.6+ manages NVIDIA GPU interop via its own Vulkan path; this flag
    # conflicts with that. Removed: ANGLE reverts to stable OpenGL (Mesa EGL) backend.
    # --enable-zero-copy: requires GBM buffer allocation, which NVIDIA proprietary
    # drivers do not support. No-op at best; removed to avoid texture sharing failures.
    "--enable-features=WebGPU,SharedArrayBuffer "
    "--enable-logging=stderr --log-level=1 "  # output captured via os.dup2 into wrapper_system.log
    "--remote-debugging-port=9222"  # Chrome DevTools at http://localhost:9222
)

import signal
import subprocess
import time
from PyQt6.QtWidgets import QApplication, QMainWindow, QColorDialog
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage, QWebEngineScript
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage
from PyQt6.QtCore import QUrl, QObject, QFile, QIODevice, QTimer, QSettings, pyqtSlot, pyqtSignal
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

        # Periodic renderer memory snapshot (every 60s)
        def _log_renderer_memory():
            try:
                import subprocess as _sp
                r = _sp.run(['pgrep', '-f', 'QtWebEngineProcess'], capture_output=True, text=True)
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
        self._mem_timer = QTimer()
        self._mem_timer.timeout.connect(_log_renderer_memory)
        self._mem_timer.start(60_000)

        self.browser.setPage(page)
        self.browser.setUrl(QUrl(f"http://localhost:{PORT}"))
        self.setCentralWidget(self.browser)
        self.resize(1280, 800)

        # Tracks the last known windowed (non-maximized) geometry so closeEvent
        # can persist it even when the window is closed while maximized. On Wayland
        # the compositor does not expose the normal geometry to the application
        # while maximized, so saveGeometry() at close time captures the maximized
        # dimensions and destroys the restore target. resizeEvent/moveEvent update
        # this only while the window is in normal state.
        self._windowed_geometry = None

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self.isMaximized() and not self.isFullScreen():
            self._windowed_geometry = self.saveGeometry()

    def moveEvent(self, event):
        super().moveEvent(event)
        if not self.isMaximized() and not self.isFullScreen():
            self._windowed_geometry = self.saveGeometry()

    def closeEvent(self, event):
        s = QSettings("odysseus", "odysseus")
        geom = self._windowed_geometry
        if geom is None and not self.isMaximized():
            geom = self.saveGeometry()
        if geom is not None:
            s.setValue("windowGeometry", geom)
        s.setValue("windowMaximized", self.isMaximized())
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

    # Restore window geometry from previous session. show() must precede
    # restoreGeometry() so the window handle exists on all platforms including
    # Wayland. On Wayland the compositor ignores restored position (by design);
    # size and maximized state both restore correctly.
    _s = QSettings("odysseus", "odysseus")
    _geom = _s.value("windowGeometry")
    if _geom:
        win.restoreGeometry(_geom)
    if _s.value("windowMaximized", False, type=bool):
        win.showMaximized()

    sys.exit(app.exec())
