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

os.environ["QT_LOGGING_RULES"] = "qt.webengine.*=true"
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
    "--enable-zero-copy --disable-gpu-compositing --ignore-gpu-blocklist "
    "--no-sandbox --use-gl=desktop --ozone-platform-hint=auto "
    f"--enable-logging --v=1 --log-file={os.path.join(LOG_DIR, 'chrome_debug.log')}"
)

import signal
import subprocess
import time
from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import QUrl

INSTALL_DIR = "/home/james/Projects/odysseus"
VENV_PYTHON = "/home/james/Projects/odysseus/venv/bin/python"
PORT = "8000"
WINDOW_TITLE = "Odysseus"

# Specific pattern that matches uvicorn but NOT this wrapper script
_UVICORN_PATTERN = "uvicorn app:app"
_server_proc = None


def kill_zombies():
    """Kill leftover uvicorn processes from a previous run, then wait for port release."""
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
    # Belt-and-suspenders: catch any orphaned uvicorn not tracked by _server_proc
    subprocess.run(["pkill", "-f", _UVICORN_PATTERN], check=False)
    print("Server stopped.")


def _signal_handler(sig, frame):
    stop_server()
    sys.exit(0)


class OdysseusWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.browser = QWebEngineView()
        self.browser.setUrl(QUrl(f"http://localhost:{PORT}"))
        self.setCentralWidget(self.browser)
        self.resize(1280, 800)

    def closeEvent(self, event):
        stop_server()
        event.accept()


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    kill_zombies()
    start_server()

    app = QApplication(sys.argv)
    win = OdysseusWindow()
    win.show()
    sys.exit(app.exec())
