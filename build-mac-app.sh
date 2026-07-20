#!/bin/bash

# ==============================================================================
# build-mac-app.sh
#
# Builds Odysseus as a native macOS desktop application.
# Creates dist/Odysseus.app (Qt WebEngine wrapper) and dist/Odysseus.dmg.
#
#   ./build-mac-app.sh            build dist/Odysseus.app + .dmg only
#   ./build-mac-app.sh --install  also install to /Applications, refresh the
#                                 icon caches, and (re-)pin to the Dock
#
# This is the Qt native wrapper installer. See build-macos-app.sh for the
# Chrome --app mode alternative (no Qt dependency, browser-based UI).
#
# The Dock tile is a macOS-style icon (dark rounded-rect on Apple's 824/1024
# grid) built from static/icons/icon-macos-1024.png. --install rebuilds the Dock
# pin as a fresh URL-only entry and clears the icon-services cache so a reinstall
# does not leave the stale/blank tile that a changed bundle inode otherwise
# causes (see tooling/macos_dock_pin.py).
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
BUNDLE_ID="com.odysseus.app"
DIST="$REPO_DIR/dist"
APP="$DIST/$APP_NAME.app"
INSTALLED_APP="/Applications/$APP_NAME.app"
VENV_PY="$REPO_DIR/venv/bin/python"
WRAPPER="$REPO_DIR/mac_wrapper.py"

# --install: after building, copy the bundle into /Applications, refresh the
# icon caches, and (re-)pin it to the Dock. Without it the script only builds
# dist/ + the .dmg (drag-to-Applications install, no Dock pin).
DO_INSTALL=0
for _arg in "$@"; do
    case "$_arg" in
        --install) DO_INSTALL=1 ;;
    esac
done

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
# Preferred source is icon-macos-1024.png — a macOS-style tile (dark #282c34
# rounded rectangle on Apple's 824/1024 icon grid, corners baked in because
# macOS does NOT auto-round app icons, with the sail glyph sized to sit on par
# with native Dock icons). It is a native 1024, so every slot including 512@2x
# downsamples cleanly. Fallbacks (SVG via rsvg, then the bare transparent
# icon-512 via sips) exist only for environments without the composed master.
ICNS_OUT="$APP/Contents/Resources/odysseus.icns"
MACOS_SRC="$REPO_DIR/static/icons/icon-macos-1024.png"
SVG_SRC="$REPO_DIR/static/icons/odysseus.svg"
PNG_SRC="$REPO_DIR/static/icons/icon-512.png"
ICON_BASE_SIZES="16 32 128 256 512"   # each emitted at 1x and @2x

# $1 = renderer (rsvg|sips), $2 = .iconset dir, $3 = source file. Renders every
# required slot; any single failure aborts so a partial iconset never reaches
# iconutil.
make_iconset() {
    local renderer="$1" set_dir="$2" src="$3" base scale px name
    mkdir -p "$set_dir" || return 1
    for base in $ICON_BASE_SIZES; do
        for scale in 1 2; do
            px=$((base * scale))
            if [ "$scale" = "1" ]; then name="icon_${base}x${base}.png"
            else name="icon_${base}x${base}@2x.png"; fi
            if [ "$renderer" = "rsvg" ]; then
                rsvg-convert -w "$px" -h "$px" "$src" -o "$set_dir/$name" >/dev/null 2>&1 || return 1
            else
                sips -z "$px" "$px" "$src" --out "$set_dir/$name" >/dev/null 2>&1 || return 1
            fi
        done
    done
}

if command -v iconutil >/dev/null 2>&1 && [ -f "$MACOS_SRC" ] && command -v sips >/dev/null 2>&1; then
    TMPSET="$(mktemp -d)/icon.iconset"
    if make_iconset sips "$TMPSET" "$MACOS_SRC" && iconutil -c icns "$TMPSET" -o "$ICNS_OUT" >/dev/null 2>&1; then
        echo "  icon: odysseus.icns (macOS tile from icon-macos-1024.png)"
    else
        echo "  icon: (iconset build from macOS master failed — non-fatal)"
    fi
    rm -rf "$(dirname "$TMPSET")"
elif command -v iconutil >/dev/null 2>&1 && [ -f "$SVG_SRC" ] && command -v rsvg-convert >/dev/null 2>&1; then
    TMPSET="$(mktemp -d)/icon.iconset"
    if make_iconset rsvg "$TMPSET" "$SVG_SRC" && iconutil -c icns "$TMPSET" -o "$ICNS_OUT" >/dev/null 2>&1; then
        echo "  icon: odysseus.icns (multi-res iconset from SVG)"
    else
        echo "  icon: (iconset build from SVG failed — non-fatal)"
    fi
    rm -rf "$(dirname "$TMPSET")"
elif command -v iconutil >/dev/null 2>&1 && [ -f "$PNG_SRC" ] && command -v sips >/dev/null 2>&1; then
    TMPSET="$(mktemp -d)/icon.iconset"
    if make_iconset sips "$TMPSET" "$PNG_SRC" && iconutil -c icns "$TMPSET" -o "$ICNS_OUT" >/dev/null 2>&1; then
        echo "  icon: odysseus.icns (multi-res iconset from 512px PNG; no macOS tile)"
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

# Mark this as a bundled launch so the wrapper leaves the Dock tile to the
# bundle's .icns instead of overriding it with setWindowIcon (which made the
# icon change — lose its background — the moment the app started).
export ODYSSEUS_BUNDLE=1
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

# --- Install to /Applications + refresh icon caches + (re-)pin to the Dock ---
# Only with --install. Reinstalling over an existing bundle changes its inode,
# which leaves BOTH the icon-services cache and the Dock pin's cached bookmark
# stale — the app then shows the old/blank icon when it is NOT running (a
# running app's tile comes from the live process, so it still looks right). The
# steps below are exactly what makes the icon correct both closed and open:
#   1. replace the installed bundle,
#   2. re-register it with Launch Services,
#   3. clear the per-user icon-services cache,
#   4. rebuild the Dock pin as a fresh URL-only entry (drops the stale bookmark
#      so the Dock re-resolves the current bundle's .icns),
#   5. restart the Dock so the new tile is drawn.
if [ "$DO_INSTALL" = "1" ]; then
    echo ""
    echo "Installing to $INSTALLED_APP ..."
    rm -rf "$INSTALLED_APP"
    cp -R "$APP" "$INSTALLED_APP"
    touch "$INSTALLED_APP"

    LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
    [ -x "$LSREGISTER" ] && "$LSREGISTER" -f "$INSTALLED_APP" 2>/dev/null || true

    # Per-user icon cache (no sudo needed); regenerated on demand.
    rm -rf "$HOME/Library/Caches/com.apple.iconservices.store" 2>/dev/null || true

    # Fresh Dock pin (drops any stale bookmark for this app).
    if [ -x "$VENV_PY" ]; then
        "$VENV_PY" "$REPO_DIR/tooling/macos_dock_pin.py" "$INSTALLED_APP" "$BUNDLE_ID" || \
            echo "  dock: (re-pin failed — non-fatal; drag the app to the Dock manually)"
    fi
    killall Dock 2>/dev/null || true
    echo "  installed, icon caches refreshed, Dock re-pinned"
fi

echo ""
echo "Done:"
echo "  $APP"
echo "  $DIST/$APP_NAME.dmg"
if [ "$DO_INSTALL" = "1" ]; then
    echo "  $INSTALLED_APP  (installed + Dock-pinned)"
fi
echo ""
echo "Run:     open '$APP'"
if [ "$DO_INSTALL" != "1" ]; then
    echo "Install: ./build-mac-app.sh --install   (to /Applications + Dock pin)"
    echo "     or: open '$DIST/$APP_NAME.dmg'  (drag Odysseus to Applications)"
fi
