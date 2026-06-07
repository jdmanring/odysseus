#!/bin/bash

# ==============================================================================
# build-linux-app.sh
#
# Builds and installs Odysseus as a native Linux desktop application.
# Follows XDG specifications for installation.
# Includes a PyQt6 native wrapper with Smart Lifecycle (PID tracking).
# ==============================================================================

set -e

# --- Configuration ---
APP_NAME="odysseus"
INSTALL_DIR="$(pwd)"
VENV_PATH="$INSTALL_DIR/venv"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor/256x256/apps"
CONFIG_DIR="$HOME/.odysseus"
PID_FILE="$CONFIG_DIR/services.pid"

# UI Settings
PORT="8000"
WINDOW_TITLE="Odysseus"

echo "🚀 Starting Odysseus Native Linux Build..."

# 1. Ensure directory structure exists
echo "📁 Creating installation directories..."
mkdir -p "$BIN_DIR"
mkdir -p "$DESKTOP_DIR"
mkdir -p "$ICON_DIR"
mkdir -p "$CONFIG_DIR"

# 2. Setup Virtual Environment
echo "📦 Setting up virtual environment in $VENV_PATH..."
python3 -m venv "$VENV_PATH"
"$VENV_PATH/bin/pip" install --upgrade pip
"$VENV_PATH/bin/pip" install -r requirements.txt
# Ensure PyQt6 is installed for the wrapper
"$VENV_PATH/bin/pip" install PyQt6 PyQt6-WebEngine

# 3. Generate the Native Wrapper Script
# This script handles the "Smart Lifecycle" (PID tracking and UI window)
echo "🛠️ Generating native PyQt6 wrapper..."
WRAPPER_PATH="$INSTALL_DIR/linux_wrapper.py"

cat <<EOF > "$WRAPPER_PATH"
import os
import sys

# ==============================================================================
# CRITICAL: These must be set BEFORE any PyQt6/QtWebEngine imports
# ==============================================================================
LOG_DIR = "/home/james/Projects/odysseus/logs"
os.makedirs(LOG_DIR, exist_ok=True)

# 1. Redirect stdout/stderr for the wrapper process (Line-buffered)
sys.stdout = open(os.path.join(LOG_DIR, "wrapper_system.log"), "a", buffering=1)
sys.stderr = open(os.path.join(LOG_DIR, "wrapper_system.log"), "a", buffering=1)

# 2. Enable Debug Logging for Qt and Chromium
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

# Configuration
INSTALL_DIR = "$INSTALL_DIR"
VENV_PYTHON = "$VENV_PATH/bin/python"
PORT = "$PORT"
WINDOW_TITLE = "$WINDOW_TITLE"

class OdysseusWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.browser = QWebEngineView()
        self.browser.setUrl(QUrl(f"http://localhost:{PORT}"))
        self.setCentralWidget(self.browser)
        self.resize(1280, 800)

    def closeEvent(self, event):
        print("🛑 Shutting down services...")
        shutdown_services()
        event.accept()

def purge_stale_services():
    # print("🧹 Nuclear Purge: Killing all odysseus processes...")
    # try:
        # Kill every process with 'odysseus' in the name
        # subprocess.run(["pkill", "-f", "odysseus"], check=False)
        # Give the OS a moment to actually release ports and GPU memory
        # time.sleep(2)
        # print("✅ Purge complete. System clean.")
    # except Exception as e:
        # print(f"Error during purge: {e}")

def start_services():
    print(f"🌐 Starting Odysseus server on port {PORT}...")
    cmd = [VENV_PYTHON, "-m", "uvicorn", "app:app", "--port", PORT]
    
    try:
        # Launch in a new session (PGID) so it's decoupled from the wrapper
        proc = subprocess.Popen(
            cmd, 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL,
            start_new_session=True 
        )
        
        # Wait for server to be ready
        timeout = 15
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                import urllib.request
                urllib.request.urlopen(f"http://localhost:{PORT}", timeout=1)
                print("✅ Server is ready!")
                return True
            except Exception:
                time.sleep(0.5)
        
        print("⚠️ Server took too long to respond, but launcher will proceed.")
        return False
    except Exception as e:
        print(f"❌ Failed to start server: {e}")
        return False

def shutdown_services():
    print("🛑 Terminating all odysseus processes...")
    subprocess.run(["pkill", "-f", "odysseus"], check=False)

if __name__ == "__main__":
    # 1. Clear the deck
    purge_stale_services()
    
    # 2. Start backend
    start_services()
    
    # 3. Launch UI
    app = QApplication(sys.argv)
    win = OdysseusWindow()
    win.show()
    sys.exit(app.exec())
EOF

# 4. Create the executable launcher in ~/.local/bin
echo "🚀 Installing executable launcher to $BIN_DIR..."
LAUNCHER_BIN="$BIN_DIR/$APP_NAME"

cat <<EOF > "$LAUNCHER_BIN"
#!/bin/bash
# Odysseus Native Launcher
"$VENV_PATH/bin/python" "$WRAPPER_PATH"
EOF

chmod +x "$LAUNCHER_BIN"

# 5. Generate the .desktop file
echo "📝 Generating desktop entry..."
DESKTOP_FILE="$DESKTOP_DIR/$APP_NAME.desktop"

cat <<EOF > "$DESKTOP_FILE"
[Desktop Entry]
Type=Application
Name=Odysseus
Comment=Personal Knowledge Graph and AI Assistant
Exec=$LAUNCHER_BIN
Icon=odysseus
Terminal=false
Categories=Office;Utility;Development;
StartupWMClass=Odysseus
EOF

# 6. Install the Icon
echo "🖼️ Installing app icon..."
if [ -f "docs/odysseus.jpg" ]; then
    # Copy and rename to the standard icon path
    cp "docs/odysseus.jpg" "$ICON_DIR/$APP_NAME.png"
    # Note: we use .png extension as it's more common for hicolor, 
    # though the source is jpg. Most DEs handle this fine.
elif [ -f "docs/odysseus.png" ]; then
    cp "docs/odysseus.png" "$ICON_DIR/$APP_NAME.png"
else
    echo "⚠️ Warning: No icon found at docs/odysseus.jpg or .png"
fi

echo "------------------------------------------------------------------------------"
echo "🎉 SUCCESS: Odysseus has been installed as a native Linux app!"
echo "------------------------------------------------------------------------------"
echo "✅ Binary: $LAUNCHER_BIN"
echo "✅ Desktop Entry: $DESKTOP_FILE"
echo "✅ Icon: $ICON_DIR/$APP_NAME.png"
echo ""
echo "You can now launch Odysseus from your application menu or by running:"
echo "  $LAUNCHER_BIN"
echo "------------------------------------------------------------------------------"
