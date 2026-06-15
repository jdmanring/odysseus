#!/bin/sh

# ==============================================================================
# build-openbsd-app.sh
#
# Installs Odysseus as a native OpenBSD desktop application (XDG spec).
#
# Prerequisites:
#   - OpenBSD amd64 or aarch64 (qt6-qtwebengine is not available for other archs)
#   - venv built with server dependencies (uvicorn, fastapi, etc.)
#   - qt_wrapper.py present in repo root (from feat/qt-native-linux-app)
#
# Install Qt WebEngine from ports (run as root or via doas):
#   doas pkg_add qt6-qtwebengine py3-pyqt6-webengine
#
# Or install into venv via pip (downloads ~250 MB Chromium binary):
#   venv/bin/pip install PyQt6 PyQt6-WebEngine
# ==============================================================================

set -e

APP_NAME="odysseus"
INSTALL_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PY="$INSTALL_DIR/venv/bin/python"
WRAPPER_PATH="$INSTALL_DIR/qt_wrapper.py"

BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"

echo "Building Odysseus native OpenBSD app from $INSTALL_DIR..."

# --- Sanity checks ---
if [ ! -f "$VENV_PY" ]; then
    echo "ERROR: venv not found at $INSTALL_DIR/venv. Run setup first." >&2
    exit 1
fi

if [ ! -f "$WRAPPER_PATH" ]; then
    echo "ERROR: qt_wrapper.py not found at $WRAPPER_PATH." >&2
    exit 1
fi

if ! "$VENV_PY" -c "import PyQt6.QtWebEngineWidgets" 2>/dev/null; then
    echo "ERROR: PyQt6 WebEngine not found." >&2
    echo "       Option 1 (system, recommended — amd64/aarch64 only):" >&2
    echo "         doas pkg_add qt6-qtwebengine py3-pyqt6-webengine" >&2
    echo "       Option 2 (venv, downloads ~250 MB Chromium binary):" >&2
    echo "         $VENV_PY -m pip install PyQt6 PyQt6-WebEngine" >&2
    exit 1
fi

echo "PyQt6 WebEngine: OK"

# --- Directories ---
mkdir -p "$BIN_DIR" "$DESKTOP_DIR" "$ICON_DIR"

# --- Launcher script ---
LAUNCHER="$BIN_DIR/$APP_NAME"
cat > "$LAUNCHER" <<LAUNCHER
#!/bin/sh
exec "$VENV_PY" "$WRAPPER_PATH"
LAUNCHER
chmod +x "$LAUNCHER"
echo "Installed launcher: $LAUNCHER"

# --- Icon ---
if [ -f "$INSTALL_DIR/assets/$APP_NAME.svg" ]; then
    cp "$INSTALL_DIR/assets/$APP_NAME.svg" "$ICON_DIR/$APP_NAME.svg"
    echo "Installed SVG icon: $ICON_DIR/$APP_NAME.svg"
fi

# --- .desktop file ---
DESKTOP_FILE="$DESKTOP_DIR/$APP_NAME.desktop"
cat > "$DESKTOP_FILE" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Odysseus
Comment=Personal AI Workspace
Exec=$LAUNCHER
Icon=$APP_NAME
Terminal=false
Categories=Office;Utility;Development;
StartupWMClass=odysseus
DESKTOP
echo "Installed desktop entry: $DESKTOP_FILE"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
fi

echo ""
echo "Done. Launch with: $LAUNCHER"
echo "Or find 'Odysseus' in your application menu."
