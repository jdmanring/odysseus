import os
import sys

# ==============================================================================
# CRITICAL: These must be set BEFORE any PyQt6/QtWebEngine imports
# ==============================================================================
LOG_DIR = "/home/james/Projects/odysseus/logs"
os.makedirs(LOG_DIR, exist_ok=True)

_log_file = open(os.path.join(LOG_DIR, "wrapper_system.log"), "a", buffering=1)
sys.stdout = _log_file
sys.stderr = _log_file

os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
    "--no-sandbox "
    "--ignore-gpu-blocklist "
    "--enable-gpu-rasterization "
    "--enable-zero-copy "
    "--enable-features=DefaultANGLEVulkan,WebGPU,SharedArrayBuffer "
    f"--enable-logging --log-file={os.path.join(LOG_DIR, 'chrome_debug.log')}"
)

import signal
import subprocess
import time
from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage
from PyQt6.QtCore import QUrl

INSTALL_DIR = "/home/james/Projects/odysseus"
VENV_PYTHON = "/home/james/Projects/odysseus/venv/bin/python"
PORT = "8000"
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
    cmd = [VENV_PYTHON, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", PORT]
    env = os.environ.copy()
    env["ODYSSEUS_LOG_FILE"] = os.path.join(LOG_DIR, "server.log")
    _server_proc = subprocess.Popen(
        cmd,
        cwd=INSTALL_DIR,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
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


class OdysseusWindow(QMainWindow):
    def __init__(self, profile: QWebEngineProfile):
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.browser = QWebEngineView()
        page = QWebEnginePage(profile, self.browser)
        self.browser.setPage(page)
        self.browser.setUrl(QUrl(f"http://localhost:{PORT}"))
        self.setCentralWidget(self.browser)
        self.resize(1280, 800)

    def closeEvent(self, event):
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
    sys.exit(app.exec())
