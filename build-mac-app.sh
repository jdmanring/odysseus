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

# Icon: build a proper multi-resolution .icns via iconutil from an .iconset.
# Rendering each size at native resolution (from the SVG when available) yields
# crisp icons at every Dock/Finder/Retina scale — the old single-size sips path
# produced one 512px image that macOS then down/up-scaled to every other slot.
# PNG fallback upscales past the 512px source, so 512@2x (1024) is softer there.
ICNS_OUT="$APP/Contents/Resources/odysseus.icns"
SVG_SRC="$REPO_DIR/static/icons/odysseus.svg"
PNG_SRC="$REPO_DIR/static/icons/icon-512.png"
ICON_BASE_SIZES="16 32 128 256 512"   # each emitted at 1x and @2x

# $1 = kind (svg|png), $2 = .iconset dir. Renders every required slot; any
# single failure aborts so a partial iconset never reaches iconutil.
make_iconset() {
    local kind="$1" set_dir="$2" base scale px name
    mkdir -p "$set_dir" || return 1
    for base in $ICON_BASE_SIZES; do
        for scale in 1 2; do
            px=$((base * scale))
            if [ "$scale" = "1" ]; then name="icon_${base}x${base}.png"
            else name="icon_${base}x${base}@2x.png"; fi
            if [ "$kind" = "svg" ]; then
                rsvg-convert -w "$px" -h "$px" "$SVG_SRC" -o "$set_dir/$name" >/dev/null 2>&1 || return 1
            else
                sips -z "$px" "$px" "$PNG_SRC" --out "$set_dir/$name" >/dev/null 2>&1 || return 1
            fi
        done
    done
}

if command -v iconutil >/dev/null 2>&1 && [ -f "$SVG_SRC" ] && command -v rsvg-convert >/dev/null 2>&1; then
    TMPSET="$(mktemp -d)/icon.iconset"
    if make_iconset svg "$TMPSET" && iconutil -c icns "$TMPSET" -o "$ICNS_OUT" >/dev/null 2>&1; then
        echo "  icon: odysseus.icns (multi-res iconset from SVG)"
    else
        echo "  icon: (iconset build from SVG failed — non-fatal)"
    fi
    rm -rf "$(dirname "$TMPSET")"
elif command -v iconutil >/dev/null 2>&1 && [ -f "$PNG_SRC" ] && command -v sips >/dev/null 2>&1; then
    TMPSET="$(mktemp -d)/icon.iconset"
    if make_iconset png "$TMPSET" && iconutil -c icns "$TMPSET" -o "$ICNS_OUT" >/dev/null 2>&1; then
        echo "  icon: odysseus.icns (multi-res iconset from 512px PNG; 512@2x upscaled)"
    else
        echo "  icon: (iconset build from PNG failed — non-fatal)"
    fi
    rm -rf "$(dirname "$TMPSET")"
else
    echo "  icon: (skipped — need iconutil + either rsvg-convert+SVG or sips+PNG)"
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

# --- Ad-hoc code signature ---
# Gives the bundle a stable local identity and reduces quarantine friction (e.g.
# Gatekeeper "damaged/incomplete" stops after the app is modified in place, and
# keeping any TCC permission grants attached to a stable code identity). This is
# NOT Developer-ID signing or notarization: distributing the .dmg to another Mac
# still trips Gatekeeper — that requires an Apple Developer ID and the notary
# service. Sign before packaging so the .dmg carries the signed bundle.
if command -v codesign >/dev/null 2>&1; then
    if codesign --force --deep --sign - "$APP" >/dev/null 2>&1; then
        if codesign -dv "$APP" 2>&1 | grep -q "Signature=adhoc"; then
            echo "  codesign: ad-hoc signature applied (NOT Gatekeeper/notarized)"
        else
            echo "  codesign: applied (verify: codesign -dv '$APP')"
        fi
    else
        echo "  codesign: (ad-hoc signing failed — non-fatal)"
    fi
fi

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
