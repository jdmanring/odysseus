# Implementation Plan: OpenBSD Native Wrapper (PyQt6)

**Fork issue:** [#46](https://github.com/jdmanring/odysseus/issues/46)
**Branch origin:** `upstream-mirror` (upstream-candidate)
**Branch name:** `feat/qt-native-openbsd-app`
**Depends on:** Issue #14 (`feat/qt-native-linux-app`) and issue #45 (`feat/qt-native-freebsd-app`)

---

## Overview

Extend `qt_wrapper.py` with OpenBSD support. `qt6-qtwebengine` (v6.8.3p4) is in
OpenBSD ports for amd64 and aarch64. OpenBSD's Chromium port uses `pledge(2)` and
`unveil(2)` for sandboxing instead of Linux's seccomp-bpf; the wrapper's existing
`--no-sandbox` flag disables the Linux-specific sandbox path and is the correct flag
for non-Linux systems.

This is likely a ~10-line change on top of the FreeBSD fix (#45), not a new file.
If #45 is filed first, OpenBSD support may be folded into the same PR or filed as a
follow-on.

---

## Architecture Note

The port is amd64 and aarch64 only. i386 and sparc64 OpenBSD users have no Qt WebEngine
port; they'd need a browser-based workflow. The PR should note this constraint.

---

## What Already Works on OpenBSD

- `os.dup2`: POSIX, works on OpenBSD
- `signal.SIGTERM` / `signal.SIGINT`: works on OpenBSD
- `QSettings("odysseus", "odysseus")`: Qt respects `XDG_CONFIG_HOME`; defaults
  to `~/.config/odysseus/odysseus.conf`
- `QDBusConnection.sessionBus()`: D-Bus available in OpenBSD ports (`devel/dbus`);
  XDG portal fallback to `QColorDialog` handles cases where portal is absent
- `app.setDesktopFileName("odysseus")`: works on OpenBSD X11/Wayland DEs
- `--no-sandbox`: already in flags; correct for OpenBSD's pledge/unveil approach
- `_is_nvidia` detection: `/proc/driver/nvidia` won't exist (OpenBSD `/proc` is
  optional and not typically mounted); returns `False` -> Mesa path -> correct

---

## Required Changes

### 1. Memory monitor platform guard

Same fix as FreeBSD (#45). `/proc/{pid}/status` is Linux-specific. On OpenBSD,
`/proc` is not typically mounted. The `platform.system() == 'Linux'` guard from
#45 automatically covers OpenBSD (it will use the `ps -o rss= -p {pid}` path).

No additional change needed if #45 is already applied.

### 2. `pkill` / `pgrep` availability

`pgrep` and `pkill` are not in OpenBSD base; they come from the `sysutils/proctools`
port. The `kill_zombies()` and `_log_renderer_memory()` functions use both. Add a
graceful fallback:

```python
def kill_zombies():
    # pkill may not be available on OpenBSD without sysutils/proctools
    try:
        result = subprocess.run(["pkill", "-f", _UVICORN_PATTERN], check=False)
        if result.returncode == 0:
            print("Killed stale uvicorn process(es), waiting for port to release...")
            time.sleep(1)
    except FileNotFoundError:
        # pkill not installed; best-effort via Python (the tracked _server_proc
        # handle is the reliable cleanup path anyway)
        pass
```

And in `_log_renderer_memory()`, add a `FileNotFoundError` catch around the
`pgrep` call:

```python
try:
    r = _sp.run(['pgrep', '-f', 'QtWebEngineProcess'], capture_output=True, text=True)
except FileNotFoundError:
    return  # pgrep not installed; skip memory logging
```

---

## `build-openbsd-app.sh`

```bash
#!/bin/bash
# Installs Odysseus as a native OpenBSD desktop application.
#
# Prerequisites:
#   - OpenBSD amd64 or aarch64 (qt6-qtwebengine not available for other archs)
#   - venv built with server dependencies
#
# Install Qt WebEngine from ports (as root or via doas):
#   doas pkg_add qt6-qtwebengine py3-pyqt6-webengine
#
# Or install into venv via pip (downloads Chromium binary, ~250 MB):
#   venv/bin/pip install PyQt6 PyQt6-WebEngine

set -e
INSTALL_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PY="$INSTALL_DIR/venv/bin/python"

if [ ! -f "$VENV_PY" ]; then
    echo "ERROR: venv not found. Run setup first." >&2; exit 1
fi

if ! "$VENV_PY" -c "import PyQt6.QtWebEngineWidgets" 2>/dev/null; then
    echo "ERROR: PyQt6 WebEngine not found." >&2
    echo "       Option 1 (system, recommended):" >&2
    echo "         doas pkg_add qt6-qtwebengine py3-pyqt6-webengine" >&2
    echo "       Option 2 (venv, downloads ~250 MB Chromium):" >&2
    echo "         $VENV_PY -m pip install PyQt6 PyQt6-WebEngine" >&2
    exit 1
fi

BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
mkdir -p "$BIN_DIR" "$DESKTOP_DIR" "$ICON_DIR"

LAUNCHER="$BIN_DIR/odysseus"
cat > "$LAUNCHER" <<LAUNCHER
#!/bin/sh
exec "$VENV_PY" "$INSTALL_DIR/qt_wrapper.py"
LAUNCHER
chmod +x "$LAUNCHER"
echo "Installed launcher: $LAUNCHER"

if [ -f "$INSTALL_DIR/static/icons/odysseus.svg" ]; then
    cp "$INSTALL_DIR/static/icons/odysseus.svg" "$ICON_DIR/odysseus.svg"
fi

cat > "$DESKTOP_DIR/odysseus.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Odysseus
Comment=Personal AI Workspace
Exec=$LAUNCHER
Icon=odysseus
Terminal=false
Categories=Office;Utility;Development;
DESKTOP

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
fi

echo "Done. Launch with: $LAUNCHER"
echo "Or find 'Odysseus' in your application menu."
```

---

## Implementation Steps

1. `git checkout upstream-mirror && git checkout -b feat/qt-native-openbsd-app`
2. Apply `pkill`/`pgrep` `FileNotFoundError` guards to `qt_wrapper.py`
   (if #45 platform guard is already merged, only these two small catches are needed)
3. Create `build-openbsd-app.sh` and `chmod +x build-openbsd-app.sh`
4. Test on an OpenBSD amd64 machine:
   - `doas pkg_add qt6-qtwebengine py3-pyqt6-webengine`
   - `python3 qt_wrapper.py`; confirm UI loads
   - Confirm `pkill`/`pgrep` fallback works without `proctools` installed
   - Install `sysutils/proctools` and confirm memory logging works with it present
5. Write PR draft at `docs/fork/upstream/pr-drafts/feat-qt-native-openbsd-app.md`
6. Cherry-pick to `develop`; mark issue #46 in-progress

---

## Testing Checklist

- [ ] App launches on OpenBSD amd64; Odysseus UI loads
- [ ] `--no-sandbox` flag present; no sandbox-related crash
- [ ] Login state persists across restarts
- [ ] External links open in system browser
- [ ] Color picker opens (QColorDialog; portal unlikely on base OpenBSD desktop)
- [ ] Window size and maximized state restore correctly
- [ ] `kill_zombies()` runs without error when `pkill` is absent
- [ ] Memory logging runs without error when `pgrep` is absent
- [ ] With `proctools` installed: memory log lines appear correctly
- [ ] Linux behavior unchanged after the guard edits

---

## PR Filing Notes

- Depends on #14 and #45. If filing before those merge, include the full wrapper
  and FreeBSD platform guard.
- Note the amd64/aarch64 constraint clearly. i386 users have no Qt WebEngine port.
- Reference upstream issue #606 and PR #3310 (Electron wrapper): explain why
  Qt WebEngine is preferable (same Chromium, 35-50% less RAM, no Node.js, direct
  Python integration, full server lifecycle management).
- D-Bus / XDG portal may be absent on minimal OpenBSD desktops; `QColorDialog`
  fallback handles this transparently.
