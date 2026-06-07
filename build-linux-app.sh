#!/bin/bash

# ==============================================================================
# build-linux-app.sh
#
# Installs Odysseus as a native Linux desktop application (XDG spec).
# Requires: venv already built, linux_wrapper.py present in repo root.
# ==============================================================================

set -e

APP_NAME="odysseus"
INSTALL_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PATH="$INSTALL_DIR/venv"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
ICON_DIR_SCALABLE="$HOME/.local/share/icons/hicolor/scalable/apps"
WRAPPER_PATH="$INSTALL_DIR/linux_wrapper.py"
PORT="8000"

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

# --- Directories ---
mkdir -p "$BIN_DIR" "$DESKTOP_DIR" "$ICON_DIR_SCALABLE"

# --- Launcher script ---
LAUNCHER_BIN="$BIN_DIR/$APP_NAME"
cat > "$LAUNCHER_BIN" <<LAUNCHER
#!/bin/bash
exec "$VENV_PATH/bin/python" "$WRAPPER_PATH"
LAUNCHER
chmod +x "$LAUNCHER_BIN"
echo "Installed launcher: $LAUNCHER_BIN"

# --- Icon (SVG preferred; fallback to PNG/JPG converted via ImageMagick) ---
ICON_PATH="$ICON_DIR_SCALABLE/$APP_NAME.svg"
if [ -f "$INSTALL_DIR/docs/$APP_NAME.svg" ]; then
    cp "$INSTALL_DIR/docs/$APP_NAME.svg" "$ICON_PATH"
    echo "Installed SVG icon: $ICON_PATH"
elif [ -f "$INSTALL_DIR/docs/$APP_NAME.png" ]; then
    # Convert to SVG container or just copy to a size-specific dir
    ICON_DIR_256="$HOME/.local/share/icons/hicolor/256x256/apps"
    mkdir -p "$ICON_DIR_256"
    cp "$INSTALL_DIR/docs/$APP_NAME.png" "$ICON_DIR_256/$APP_NAME.png"
    ICON_PATH="$ICON_DIR_256/$APP_NAME.png"
    echo "Installed PNG icon: $ICON_PATH"
elif [ -f "$INSTALL_DIR/docs/$APP_NAME.jpg" ]; then
    # Convert JPG → PNG using ImageMagick if available, otherwise skip
    ICON_DIR_256="$HOME/.local/share/icons/hicolor/256x256/apps"
    mkdir -p "$ICON_DIR_256"
    if command -v convert &>/dev/null; then
        convert -resize 256x256 "$INSTALL_DIR/docs/$APP_NAME.jpg" "$ICON_DIR_256/$APP_NAME.png"
        ICON_PATH="$ICON_DIR_256/$APP_NAME.png"
        echo "Converted and installed PNG icon: $ICON_PATH"
    else
        echo "WARNING: docs/$APP_NAME.jpg found but ImageMagick (convert) not available." >&2
        echo "         No icon installed. Install imagemagick or provide a .svg/.png." >&2
    fi
else
    echo "WARNING: No icon found in docs/ ($APP_NAME.svg/.png/.jpg). Skipping." >&2
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

# Refresh icon cache so KDE/GNOME picks up the new icon immediately
if command -v gtk-update-icon-cache &>/dev/null; then
    gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
fi
if command -v update-desktop-database &>/dev/null; then
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
fi

echo ""
echo "Done. Launch with:  $LAUNCHER_BIN"
echo "Or find 'Odysseus' in your application menu (may need to log out/in on KDE)."
