#!/bin/bash

# ==============================================================================
# build-freebsd-app.sh
#
# Installs Odysseus as a native FreeBSD desktop application (XDG spec).
# Primary target: KDE Plasma on FreeBSD. Also works on GhostBSD/MATE and
# other FreeBSD desktops (XFCE, LXQt, etc.).
#
# Prerequisites:
#   - venv built with server dependencies (uvicorn, fastapi, etc.)
#   - System PyQt6 with WebEngine installed via pkg:
#       pkg install py311-qt6-webengine py311-qt6-webchannel py311-dbus-python
#     or into venv via pip (downloads ~250 MB Chromium binary):
#       venv/bin/pip install PyQt6 PyQt6-WebEngine
#   - qt_wrapper.py present in repo root (from feat/qt-native-linux-app)
#
# The display layer (qt_wrapper.py) can use either the system python3 (if
# system PyQt6 is installed) or the venv python. This script uses the venv
# python and falls back to system python3 if PyQt6 is not in the venv.
# ==============================================================================

set -e

APP_NAME="odysseus"
INSTALL_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PATH="$INSTALL_DIR/venv"
VENV_PYTHON="$VENV_PATH/bin/python"
SYSTEM_PYTHON="/usr/local/bin/python3"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
ICON_DIR_SCALABLE="$HOME/.local/share/icons/hicolor/scalable/apps"
WRAPPER_PATH="$INSTALL_DIR/qt_wrapper.py"

echo "Building Odysseus native FreeBSD app from $INSTALL_DIR..."

# --- Sanity checks ---
if [ ! -f "$VENV_PATH/bin/python" ]; then
    echo "ERROR: venv not found at $VENV_PATH. Run setup first." >&2
    exit 1
fi

if [ ! -f "$WRAPPER_PATH" ]; then
    echo "ERROR: qt_wrapper.py not found at $WRAPPER_PATH." >&2
    exit 1
fi

# Prefer venv python if PyQt6 is installed there; fall back to system python3
if "$VENV_PYTHON" -c "import PyQt6.QtWebEngineWidgets" 2>/dev/null; then
    WRAPPER_PYTHON="$VENV_PYTHON"
    echo "Using venv PyQt6."
elif "$SYSTEM_PYTHON" -c "import PyQt6.QtWebEngineWidgets" 2>/dev/null; then
    WRAPPER_PYTHON="$SYSTEM_PYTHON"
    echo "Using system PyQt6."
else
    echo "ERROR: PyQt6 with WebEngine not found in venv or system python3." >&2
    echo "       Option 1 (system, recommended on FreeBSD):" >&2
    echo "         pkg install py311-qt6-webengine py311-qt6-webchannel py311-dbus-python" >&2
    echo "       Option 2 (venv, downloads ~250 MB Chromium binary):" >&2
    echo "         $VENV_PYTHON -m pip install PyQt6 PyQt6-WebEngine" >&2
    exit 1
fi

echo "PyQt6 WebEngine: OK"

# --- Directories ---
mkdir -p "$BIN_DIR" "$DESKTOP_DIR" "$ICON_DIR_SCALABLE"

# --- Launcher script ---
LAUNCHER_BIN="$BIN_DIR/$APP_NAME"
cat > "$LAUNCHER_BIN" <<LAUNCHER
#!/bin/sh
exec "$WRAPPER_PYTHON" "$WRAPPER_PATH"
LAUNCHER
chmod +x "$LAUNCHER_BIN"
echo "Installed launcher: $LAUNCHER_BIN"

# --- Icon ---
ICON_PATH="$ICON_DIR_SCALABLE/$APP_NAME.svg"
if [ -f "$INSTALL_DIR/assets/$APP_NAME.svg" ]; then
    cp "$INSTALL_DIR/assets/$APP_NAME.svg" "$ICON_PATH"
    echo "Installed SVG icon: $ICON_PATH"
elif [ -f "$INSTALL_DIR/assets/$APP_NAME.png" ]; then
    ICON_DIR_256="$HOME/.local/share/icons/hicolor/256x256/apps"
    mkdir -p "$ICON_DIR_256"
    cp "$INSTALL_DIR/assets/$APP_NAME.png" "$ICON_DIR_256/$APP_NAME.png"
    echo "Installed PNG icon: $ICON_DIR_256/$APP_NAME.png"
else
    echo "WARNING: No icon found in assets/ ($APP_NAME.svg/.png). Skipping." >&2
fi

# --- .desktop file ---
DESKTOP_FILE="$DESKTOP_DIR/$APP_NAME.desktop"
cat > "$DESKTOP_FILE" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Odysseus
Comment=Personal AI Workspace
Exec=$LAUNCHER_BIN
Icon=$APP_NAME
Terminal=false
Categories=Office;Utility;Development;
StartupWMClass=odysseus
DESKTOP
echo "Installed desktop entry: $DESKTOP_FILE"

# Refresh desktop and icon caches
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
fi
if command -v kbuildsycoca6 >/dev/null 2>&1; then
    kbuildsycoca6 2>/dev/null || true
fi

echo ""
echo "Done. Launch with:  $LAUNCHER_BIN"
echo "Or find 'Odysseus' in your application menu."
if command -v kbuildsycoca6 >/dev/null 2>&1; then
    echo "Note: Log out and back in for KDE to pick up the new icon and launcher."
fi
