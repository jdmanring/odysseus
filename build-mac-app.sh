#!/bin/bash

# ==============================================================================
# build-mac-app.sh
#
# Installs Odysseus as a native macOS desktop application.
# Creates dist/Odysseus.app (Qt WebEngine wrapper) and dist/Odysseus.dmg.
#
# This is the Qt native wrapper installer. See build-macos-app.sh for the
# Chrome --app mode alternative (no Qt dependency, browser-based UI).
#
# Prerequisites:
#   - macOS 11.0+, arm64 or x86_64
#   - venv built with server dependencies (uvicorn, fastapi, etc.)
#   - mac_wrapper.py present in repo root (from feat/qt-native-macos-app)
#   PyQt6 WebEngine is installed into the venv by this script if not present.
# ==============================================================================

set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="Odysseus"
DIST="$REPO_DIR/dist"
APP="$DIST/$APP_NAME.app"
VENV_PY="$REPO_DIR/venv/bin/python"
WRAPPER="$REPO_DIR/mac_wrapper.py"

# macOS dialog for fatal errors (visible even when launched as .app)
die_gui() {
    /usr/bin/osascript -e \
        "display dialog \"$1\" with title \"Odysseus\" buttons {\"OK\"} default button 1 with icon stop" \
        >/dev/null 2>&1 || true
    echo "ERROR: $1" >&2
    exit 1
}

echo "Building $APP_NAME.app (Qt WebEngine wrapper)..."

# --- Sanity checks ---
if [ ! -f "$VENV_PY" ]; then
    die_gui "venv not found at $REPO_DIR/venv. Run setup first:
cd $REPO_DIR && python3 -m venv venv && ./venv/bin/pip install -r requirements.txt"
fi

if [ ! -f "$WRAPPER" ]; then
    die_gui "mac_wrapper.py not found at $REPO_DIR.
This script requires the feat/qt-native-macos-app branch."
fi

# Install PyQt6 WebEngine if not already in the venv
if ! "$VENV_PY" -c "import PyQt6.QtWebEngineWidgets" 2>/dev/null; then
    echo "PyQt6 WebEngine not found — installing (~250 MB download)..."
    "$VENV_PY" -m pip install --quiet PyQt6 PyQt6-WebEngine PyQt6-sip
fi

echo "PyQt6 WebEngine: OK"

# --- Build .app bundle ---
mkdir -p "$DIST"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

# Icon: try SVG → icns, fall back to JPEG via sips
if [ -f "$REPO_DIR/assets/$APP_NAME.svg" ] && command -v rsvg-convert >/dev/null 2>&1; then
    TMPIMG="$(mktemp -d)"
    rsvg-convert -w 512 -h 512 "$REPO_DIR/assets/odysseus.svg" \
        -o "$TMPIMG/icon.png" >/dev/null 2>&1 && \
    sips -s format icns "$TMPIMG/icon.png" \
        --out "$APP/Contents/Resources/odysseus.icns" >/dev/null 2>&1 || true
    rm -rf "$TMPIMG"
    echo "  icon: odysseus.icns (from SVG)"
elif [ -f "$REPO_DIR/docs/odysseus.jpg" ] && command -v sips >/dev/null 2>&1; then
    TMPIMG="$(mktemp -d)"
    sips -c 720 720 "$REPO_DIR/docs/odysseus.jpg" \
        --out "$TMPIMG/sq.png" >/dev/null 2>&1 \
        || cp "$REPO_DIR/docs/odysseus.jpg" "$TMPIMG/sq.png"
    sips -z 512 512 "$TMPIMG/sq.png" --out "$TMPIMG/icon.png" >/dev/null 2>&1
    sips -s format icns "$TMPIMG/icon.png" \
        --out "$APP/Contents/Resources/odysseus.icns" >/dev/null 2>&1 || true
    rm -rf "$TMPIMG"
    echo "  icon: odysseus.icns (from JPEG)"
else
    echo "  icon: (skipped — no assets/odysseus.svg or docs/odysseus.jpg)"
fi

# Info.plist
# NSSupportsAutomaticGraphicsSwitching: enables discrete/integrated GPU hand-off
# on dual-GPU MacBooks (required for Qt WebEngine Metal backend, Qt 6.5+).
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>                         <string>$APP_NAME</string>
    <key>CFBundleDisplayName</key>                  <string>$APP_NAME</string>
    <key>CFBundleIdentifier</key>                   <string>com.odysseus.app</string>
    <key>CFBundleVersion</key>                      <string>1.0</string>
    <key>CFBundleShortVersionString</key>           <string>1.0</string>
    <key>CFBundlePackageType</key>                  <string>APPL</string>
    <key>CFBundleExecutable</key>                   <string>$APP_NAME</string>
    <key>CFBundleIconFile</key>                     <string>odysseus</string>
    <key>LSMinimumSystemVersion</key>               <string>11.0</string>
    <key>NSHighResolutionCapable</key>              <true/>
    <key>NSSupportsAutomaticGraphicsSwitching</key> <true/>
    <key>LSUIElement</key>                          <false/>
</dict>
</plist>
PLIST

# Launcher — exec's into mac_wrapper.py which owns the full server + window lifecycle.
# Using a template so REPO_DIR is baked in at build time (same approach as build-macos-app.sh).
cat > "$APP/Contents/MacOS/$APP_NAME.tmpl" <<'LAUNCHER'
#!/bin/bash
REPO_DIR="__REPO_DIR__"
VENV_PY="$REPO_DIR/venv/bin/python"
WRAPPER="$REPO_DIR/mac_wrapper.py"

die_gui() {
    /usr/bin/osascript -e \
        "display dialog \"$1\" with title \"Odysseus\" buttons {\"OK\"} default button 1 with icon stop" \
        >/dev/null 2>&1 || true
    exit 1
}

[ -x "$VENV_PY" ] || die_gui "venv not found at $REPO_DIR/venv.

Open Terminal and run:
  cd $REPO_DIR
  python3 -m venv venv && ./venv/bin/pip install -r requirements.txt"

[ -f "$WRAPPER" ] || die_gui "mac_wrapper.py not found at $REPO_DIR.
Reinstall Odysseus or check the installation."

exec "$VENV_PY" "$WRAPPER"
LAUNCHER

sed "s|__REPO_DIR__|$REPO_DIR|g" \
    "$APP/Contents/MacOS/$APP_NAME.tmpl" > "$APP/Contents/MacOS/$APP_NAME"
rm -f "$APP/Contents/MacOS/$APP_NAME.tmpl"
chmod +x "$APP/Contents/MacOS/$APP_NAME"

# Refresh Finder's bundle cache
touch "$APP"

echo ""
echo "Built: $APP"

# --- .dmg (drag-to-Applications installer) ---
echo "Packaging $DIST/$APP_NAME.dmg..."
STAGE="$(mktemp -d)/dmg"
mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
rm -f "$DIST/$APP_NAME.dmg"
hdiutil create -volname "$APP_NAME" -srcfolder "$STAGE" -ov -format UDZO \
    "$DIST/$APP_NAME.dmg" >/dev/null
rm -rf "$STAGE"

echo ""
echo "Done:"
echo "  $APP"
echo "  $DIST/$APP_NAME.dmg"
echo ""
echo "Run:     open '$APP'"
echo "Install: open '$DIST/$APP_NAME.dmg'  (drag Odysseus to Applications)"
