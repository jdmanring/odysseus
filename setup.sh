#!/bin/sh
# ==============================================================================
# setup.sh — one-command from-scratch setup for Linux / FreeBSD / OpenBSD.
#
#   ./setup.sh
#
# Provisions the Python environment and installs the native desktop app, so a
# fresh checkout goes to an installed app in one command — the equivalent of
# macOS's start-macos.sh. It:
#   1. finds a Python 3.11+ for the backend venv,
#   2. checks for SYSTEM PyQt6/WebEngine (the display layer runs under the
#      system python3 for native Wayland — see build-linux-app.sh),
#   3. creates venv/ and installs requirements.txt (idempotent),
#   4. runs first-run setup (data dirs + initial admin password),
#   5. builds + installs the native desktop app via ./install.sh.
#
# POSIX sh (runs on OpenBSD's /bin/sh too). Per policy this never runs a
# privileged command itself: when a SYSTEM package is required (Python or Qt,
# which need root to install) it prints the exact package-manager command and
# stops, so the single privileged step is yours to run.
#
#   macOS   → use ./start-macos.sh  (sets up + launches), then ./install.sh
#   Windows → use setup.ps1
# ==============================================================================
set -e
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_DIR"

OS="$(uname -s)"
case "$OS" in
    Linux | FreeBSD | OpenBSD) : ;;
    Darwin)
        echo "macOS: run ./start-macos.sh (sets up + launches in your browser),"
        echo "       then ./install.sh for the native .app. (setup.sh covers Linux/*BSD.)"
        exit 0
        ;;
    *)
        echo "Unsupported OS: $OS. On Windows run setup.ps1." >&2
        exit 1
        ;;
esac

echo "==> Odysseus setup ($OS)"

# Package-manager-specific install hints (we print, never run — needs root).
QT_HINT=""
PY_HINT=""
if command -v pacman >/dev/null 2>&1; then
    QT_HINT="sudo pacman -S python-pyqt6 python-pyqt6-webengine"
    PY_HINT="sudo pacman -S python"
elif command -v apt >/dev/null 2>&1; then
    QT_HINT="sudo apt install python3-pyqt6 python3-pyqt6.qtwebengine"
    PY_HINT="sudo apt install python3 python3-venv"
elif command -v dnf >/dev/null 2>&1; then
    QT_HINT="sudo dnf install python3-pyqt6 python3-pyqt6-webengine"
    PY_HINT="sudo dnf install python3"
elif command -v zypper >/dev/null 2>&1; then
    QT_HINT="sudo zypper install python3-PyQt6 python3-PyQt6-WebEngine"
    PY_HINT="sudo zypper install python3"
elif [ "$OS" = "FreeBSD" ] && command -v pkg >/dev/null 2>&1; then
    QT_HINT="doas pkg install py311-qt6-webengine py311-qt6-webchannel py311-dbus-python"
    PY_HINT="doas pkg install python311"
elif [ "$OS" = "OpenBSD" ] && command -v pkg_add >/dev/null 2>&1; then
    QT_HINT="doas pkg_add qt6-qtwebengine py3-pyqt6-webengine"
    PY_HINT="doas pkg_add python%3.11"
fi

# 1. Python 3.11+ for the backend venv.
PY=""
for cand in python3 python3.13 python3.12 python3.11; do
    p="$(command -v "$cand" 2>/dev/null)" || continue
    if "$p" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 11) else 1)' 2>/dev/null; then
        PY="$p"
        break
    fi
done
if [ -z "$PY" ]; then
    echo "x  Need Python 3.11+ (for the backend venv)." >&2
    [ -n "$PY_HINT" ] && echo "   Install it, then re-run ./setup.sh:  $PY_HINT" >&2
    exit 1
fi
echo "   ok Python: $("$PY" --version 2>&1)  ($PY)"

# 2. SYSTEM PyQt6/WebEngine for the display layer. On Linux/*BSD the native
#    wrapper runs under /usr/bin/python3 (not the venv) for native Wayland, so
#    PyQt6 must be a system package — installing it needs root, so we print the
#    command and stop rather than run it (and rather than pip it into the venv,
#    which the system python3 could not import anyway).
if ! /usr/bin/python3 -c "import PyQt6.QtWebEngineWidgets" 2>/dev/null; then
    echo "" >&2
    echo "x  System PyQt6 WebEngine is required for the native $OS app." >&2
    echo "   (The display layer runs under /usr/bin/python3 for native Wayland." >&2
    echo "    Do NOT pip-install it — the system python3 cannot import venv packages.)" >&2
    echo "   Install it, then re-run ./setup.sh:" >&2
    echo "     ${QT_HINT:-<your package manager>: PyQt6 + PyQt6-WebEngine}" >&2
    exit 1
fi
echo "   ok System PyQt6 WebEngine"

# 3. Backend venv + requirements (venv holds ONLY server deps, NOT PyQt6).
#    Idempotent: skip pip when requirements.txt is unchanged since the last run.
if [ ! -x venv/bin/python ] || ! venv/bin/python -m pip --version >/dev/null 2>&1; then
    [ -d venv ] && { echo "==> Rebuilding incomplete venv…"; rm -rf venv; }
    echo "==> Creating Python environment (venv/)…"
    "$PY" -m venv venv
fi
REQ_HASH="$(cksum requirements.txt | cut -d' ' -f1)"
if [ "$REQ_HASH" != "$(cat venv/.requirements_hash 2>/dev/null || true)" ]; then
    echo "==> Installing Python packages (first run can take a few minutes)…"
    venv/bin/python -m pip install --quiet --upgrade pip
    venv/bin/python -m pip install -r requirements.txt
    echo "$REQ_HASH" > venv/.requirements_hash
else
    echo "   ok Python packages up to date"
fi

# 3b. Verify the memory / RAG stack (chromadb + fastembed) actually loads. pip
#     installs them, but fastembed's onnxruntime has native prerequisites pip
#     can't provide, and a silent failure demotes semantic memory to keyword
#     search. Warn (don't abort — the app still runs degraded) with a fix.
if ! venv/bin/python tooling/verify_memory_stack.py; then
    echo "   (install continues; the app runs with keyword-only memory until fixed)" >&2
fi

# 4. First-run setup (data dirs + initial admin password; idempotent).
echo "==> Preparing Odysseus…"
ODYSSEUS_SKIP_RUN_HINT=1 venv/bin/python setup.py

# 5. Build + install the native desktop app (install.sh dispatches by uname).
echo "==> Installing the native desktop app…"
exec ./install.sh "$@"
