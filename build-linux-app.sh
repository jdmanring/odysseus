#!/bin/bash

# ==============================================================================
# build-linux-app.sh
#
# Installs Odysseus as a native Linux desktop application (XDG spec).
#
# Prerequisites:
#   - venv built with server dependencies (uvicorn, fastapi, etc.)
#   - System PyQt6 with Wayland support installed via pacman:
#       sudo pacman -S python-pyqt6 python-pyqt6-webengine
#   - linux_wrapper.py present in repo root
#
# The display layer (linux_wrapper.py) runs under the SYSTEM python3 so it
# can use the system-built PyQt6/WebEngine with native Wayland support.
# The backend (uvicorn) runs under the venv python where all server deps live.
# ==============================================================================

set -e

APP_NAME="odysseus"
INSTALL_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PATH="$INSTALL_DIR/venv"
SYSTEM_PYTHON="/usr/bin/python3"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
ICON_DIR_SCALABLE="$HOME/.local/share/icons/hicolor/scalable/apps"
WRAPPER_PATH="$INSTALL_DIR/linux_wrapper.py"

echo "Building Odysseus native Linux app from $INSTALL_DIR..."

# --- Sanity checks ---
if [ ! -f "$VENV_PATH/bin/python" ]; then
    echo "ERROR: venv not found at $VENV_PATH. Run setup first." >&2
    exit 1
fi

if [ ! -f "$WRAPPER_PATH" ]; then
    echo "ERROR: linux_wrapper.py not found at $WRAPPER_PATH." >&2
    exit 1
fi

if ! "$SYSTEM_PYTHON" -c "import PyQt6.QtWebEngineWidgets" 2>/dev/null; then
    echo "ERROR: System PyQt6 with WebEngine not found." >&2
    echo "       Install it: sudo pacman -S python-pyqt6 python-pyqt6-webengine" >&2
    exit 1
fi

echo "System PyQt6: OK"

# --- Directories ---
mkdir -p "$BIN_DIR" "$DESKTOP_DIR" "$ICON_DIR_SCALABLE"

# --- Launcher script ---
# Uses system python3 for the wrapper (native Wayland via system-built PyQt6).
# The wrapper itself spawns the backend under the venv python.
LAUNCHER_BIN="$BIN_DIR/$APP_NAME"
cat > "$LAUNCHER_BIN" <<LAUNCHER
#!/bin/bash
exec "$SYSTEM_PYTHON" "$WRAPPER_PATH"
LAUNCHER
chmod +x "$LAUNCHER_BIN"
echo "Installed launcher: $LAUNCHER_BIN"

# --- Icon (static/icons/ holds the scalable SVG and PNG sizes) ---
ICON_PATH="$ICON_DIR_SCALABLE/odysseus.svg"
if [ -f "$INSTALL_DIR/static/icons/odysseus.svg" ]; then
    cp "$INSTALL_DIR/static/icons/odysseus.svg" "$ICON_PATH"
    echo "Installed SVG icon: $ICON_PATH"
elif [ -f "$INSTALL_DIR/static/icons/icon-512.png" ]; then
    ICON_DIR_256="$HOME/.local/share/icons/hicolor/256x256/apps"
    mkdir -p "$ICON_DIR_256"
    cp "$INSTALL_DIR/static/icons/icon-512.png" "$ICON_DIR_256/odysseus.png"
    echo "Installed PNG icon: $ICON_DIR_256/odysseus.png"
else
    echo "WARNING: No icon found in static/icons/ (odysseus.svg / icon-512.png). Skipping." >&2
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
StartupWMClass=$APP_NAME
DESKTOP
echo "Installed desktop entry: $DESKTOP_FILE"

# Refresh icon and desktop caches
if command -v gtk-update-icon-cache &>/dev/null; then
    gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
fi
if command -v update-desktop-database &>/dev/null; then
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
fi
if command -v kbuildsycoca6 &>/dev/null; then
    kbuildsycoca6 2>/dev/null || true
fi

echo ""
echo "Done. Launch with:  $LAUNCHER_BIN"
echo "Or find 'Odysseus' in your application menu."
echo "Note: Log out and back in for KDE to pick up the new icon and launcher."
