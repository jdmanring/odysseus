#!/bin/bash

# ==============================================================================
# build-freebsd-app.sh
#
# Installs Odysseus as a native FreeBSD desktop application (XDG spec).
# Primary target: KDE Plasma on FreeBSD. Also works on GhostBSD/MATE and
# other FreeBSD desktops (XFCE, LXQt, etc.).
#
# Prerequisites (verified on FreeBSD 15.1, KDE Plasma):
#
#   1. System packages — prebuilt binaries, so no Rust/C source builds. PyQt6 on
#      FreeBSD is packaged for python3.12, so use that interpreter throughout.
#      These are the CORE deps that carry native code (everything else in
#      requirements.txt is pure Python and pip installs it fine):
#
#        doas pkg install \
#          py312-qt6-pyqt py312-qt6-webengine \       # PyQt6 + QtWebEngine bindings
#          py312-sqlite3 \                            # sqlite3 ext (NOT bundled in FreeBSD's python)
#          py312-pydantic2 py312-cryptography py312-bcrypt py312-nh3 \   # Rust/C deps as binaries
#          py312-numpy py312-lxml py312-pillow \      # numpy; lxml (caldav); pillow (qrcode 2FA)
#          py312-llama-cpp-python \                   # onnxruntime-free embedding backend (semantic memory)
#          aria2                                      # HF downloader backend (tooling/aria2c_download.py)
#
#   2. A venv that can SEE those system packages, then the pure-Python remainder:
#
#        python3.12 -m venv --system-site-packages venv
#        venv/bin/pip install -r requirements.txt
#
#      --system-site-packages lets the venv use the pkg-installed PyQt6 and the
#      binary Rust/C deps above, so pip only builds pure-Python wheels (no
#      compiler needed).
#
#   3. qt_wrapper.py present in repo root (shared with the Linux app).
#
# Semantic memory / RAG on FreeBSD (verified 2026-07-22): WORKING via llama.cpp.
# fastembed's runtime is onnxruntime, which has no FreeBSD Python binding (the
# pkg ships only the C++ library; there's no wheel), so fastembed itself cannot
# run here. Instead the app auto-falls-back to a llama.cpp embedding backend
# (LlamaCppEmbedClient) running the SAME model as the fleet default,
# nomic-embed-text-v1.5, as a GGUF via py312-llama-cpp-python — 768-dim, no
# onnxruntime, vectors ~0.96-compatible with the fleet's fastembed output. So
# semantic memory is full-quality here, not keyword-only. The GGUF downloads on
# first use (nomic-ai/nomic-embed-text-v1.5-GGUF, Q8_0). chromadb-client is the
# vector-store client; a reachable ChromaDB service is still required.
#
# The display layer (qt_wrapper.py) uses the venv python (which sees the pkg
# PyQt6 via --system-site-packages); it falls back to system python3.12 if PyQt6
# is not reachable from the venv.
# ==============================================================================

set -e

APP_NAME="odysseus"
INSTALL_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PATH="$INSTALL_DIR/venv"
VENV_PYTHON="$VENV_PATH/bin/python"
# PyQt6 on FreeBSD is packaged for python3.12 (py312-qt6-pyqt), so the system
# fallback interpreter must be 3.12 — a bare python3 may resolve to 3.11, which
# has no PyQt6.
SYSTEM_PYTHON="/usr/local/bin/python3.12"
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
    echo "ERROR: PyQt6 with WebEngine not found in venv or system python3.12." >&2
    echo "       Install the FreeBSD packages, then a system-site-packages venv:" >&2
    echo "         doas pkg install py312-qt6-pyqt py312-qt6-webengine py312-sqlite3 aria2" >&2
    echo "         python3.12 -m venv --system-site-packages venv" >&2
    echo "         venv/bin/pip install -r requirements.txt" >&2
    echo "       See the header of this script for the full dependency list." >&2
    exit 1
fi

echo "PyQt6 WebEngine: OK"

# Verify the memory / RAG stack (chromadb + fastembed) loads. On FreeBSD fastembed
# needs a build-time Rust toolchain (see the header); a silent failure demotes
# semantic memory to keyword search, so surface it (non-fatal — the app still runs).
"$VENV_PYTHON" "$INSTALL_DIR/tooling/verify_memory_stack.py" || \
    echo "   (build continues; install py312-llama-cpp-python for semantic memory)" >&2

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
if [ -f "$INSTALL_DIR/static/icons/$APP_NAME.svg" ]; then
    cp "$INSTALL_DIR/static/icons/$APP_NAME.svg" "$ICON_PATH"
    echo "Installed SVG icon: $ICON_PATH"
elif [ -f "$INSTALL_DIR/static/icons/icon-512.png" ]; then
    ICON_DIR_256="$HOME/.local/share/icons/hicolor/256x256/apps"
    mkdir -p "$ICON_DIR_256"
    cp "$INSTALL_DIR/static/icons/icon-512.png" "$ICON_DIR_256/$APP_NAME.png"
    echo "Installed PNG icon: $ICON_DIR_256/$APP_NAME.png"
else
    echo "WARNING: No icon found in static/icons/. Skipping." >&2
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
