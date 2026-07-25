# Implementation Plan: macOS Native Wrapper (PyQt6)

**Fork issue:** [#43](https://github.com/jdmanring/odysseus/issues/43)
**Branch origin:** `upstream-mirror` (upstream-candidate)
**Branch name:** `feat/qt-native-macos-app`
**Depends on:** Issue #14 / `feat/qt-native-linux-app` merged upstream first (shared JS bridge files)

---

## Overview

Create `mac_wrapper.py` and `build-mac-app.sh`: a native macOS desktop wrapper using
PyQt6, modeled directly on `qt_wrapper.py`. The architecture is identical; only the
platform-specific blocks differ.

Our approach is a direct alternative to upstream PR #3310 (Electron wrapper) and issue
#606. Qt WebEngine uses the same Chromium engine as Electron but without bundling Node.js,
using 35-50% less RAM, and integrating natively with the Python process that already
runs the server. The PR description should reference #606/#3310 explicitly.

---

## What Changes vs `qt_wrapper.py`

**1. LOG_DIR** (macOS convention):
```python
LOG_DIR = os.path.join(os.path.expanduser("~"), "Library", "Logs", "Odysseus")
```

**2. Remove `QTWEBENGINE_FORCE_USE_GBM`**: Linux Qt 6.9+ regression guard; not
applicable on macOS:
```python
# Remove: os.environ.setdefault("QTWEBENGINE_FORCE_USE_GBM", "0")
```

**3. Chromium flags**. macOS uses Metal natively; no GBM/Vulkan guards:
```python
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join([
    "--ignore-gpu-blocklist",
    "--enable-gpu-rasterization",
    "--enable-features=WebGPU,SharedArrayBuffer",
    "--enable-logging=stderr --log-level=1",
    "--remote-debugging-port=9222",
])
```
Removed vs Linux: `--no-sandbox` (not required on macOS), all Vulkan/GBM guards,
`--enable-zero-copy` (GBM-specific).

**4. Remove D-Bus imports**; not available on macOS:
```python
# Remove: from PyQt6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage
```

**5. PORT default**: 7860; AirPlay Receiver holds 7000 on macOS:
```python
PORT = os.environ.get("APP_PORT", "7860")
```

**6. NativeBridge**: replace the full D-Bus portal + fallback with direct QColorDialog:
```python
class NativeBridge(QObject):
    colorPicked = pyqtSignal(str)

    @pyqtSlot()
    def openColorPicker(self):
        color = QColorDialog.getColor()
        self.colorPicked.emit(color.name() if color.isValid() else '')
```

**7. `_log_renderer_memory()`**. `pgrep` works on macOS; no change needed.

**8. `app.setDesktopFileName()`**: not available on macOS. Replace with:
```python
app.setApplicationName("Odysseus")
app.setOrganizationName("Odysseus")
```

**9. QSettings**: no change. Qt writes to `~/Library/Preferences/` on macOS
automatically.

**10. VENV_PYTHON**: `venv/bin/python`; same path as Linux on macOS.

**11. DATA_DIR / CACHE_DIR**. Follow macOS convention:
```python
DATA_DIR  = os.path.expanduser("~/Library/Application Support/odysseus/webengine")
CACHE_DIR = os.path.expanduser("~/Library/Caches/odysseus/webengine")
```

---

## Files to Create

### `mac_wrapper.py`

Apply the eleven changes above to `qt_wrapper.py`. Everything else (OdysseusPage,
OdysseusWindow, QWebChannel, QWebEngineScript injection, crash recovery, window state,
server lifecycle) is identical to the Linux version.

### `build-mac-app.sh`

```bash
#!/bin/bash
# Installs Odysseus as a native macOS desktop application.
#
# Prerequisites:
#   - venv built with server dependencies
#   - PyQt6 with Qt WebEngine installed in venv (handled below)
set -e

INSTALL_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PY="$INSTALL_DIR/venv/bin/python"

if [ ! -f "$VENV_PY" ]; then
    echo "ERROR: venv not found. Run setup first." >&2; exit 1
fi

echo "Installing macOS wrapper dependencies..."
"$VENV_PY" -m pip install --quiet PyQt6 PyQt6-WebEngine PyQt6-sip

echo "Done. Launch with:  $VENV_PY $INSTALL_DIR/mac_wrapper.py"
```

> **Note:** The existing `build-macos-app.sh` builds a Chrome-based `.app` bundle.
> `build-mac-app.sh` is the native PyQt6 alternative. Both can coexist.

---

## Files Already Present (no changes needed)

Added by `feat/qt-native-linux-app`, platform-neutral:

- `static/js/qt-bridge.js`: `window.__QT_WRAPPER__` guard works on macOS unchanged
- `static/index.html`: script injection is platform-neutral
- `static/js/colorPicker.js`: `window.qtBridge.openColorPicker()` is neutral;
  the native dialog is QColorDialog on macOS

---

## Implementation Steps

1. `git checkout upstream-mirror && git checkout -b feat/qt-native-macos-app`
2. Create `mac_wrapper.py` per the spec above
3. Create `build-mac-app.sh` and `chmod +x build-mac-app.sh`
4. Run `bash build-mac-app.sh` then `venv/bin/python mac_wrapper.py` on a macOS machine
5. Test checklist below
6. Screenshot the running app for the PR
7. Write PR draft at `docs/fork/upstream/pr-drafts/feat-qt-native-macos-app.md`
   (model on `feat-qt-native-linux-app.md`; reference issues #43, #606, PR #3310)
8. Cherry-pick to `develop`; mark issue #43 in-progress

---

## Testing Checklist

- [ ] App launches; Odysseus UI loads in a native macOS window
- [ ] Server starts on port 7860; no conflict with AirPlay Receiver
- [ ] Login persists after closing and reopening
- [ ] External link opens in system browser (Safari/Chrome), not inside the wrapper
- [ ] Color picker opens `QColorDialog` macOS native dialog
- [ ] Window size and maximized state restore correctly on reopen
- [ ] Chrome DevTools available at `http://localhost:9222`
- [ ] Logs appear in `~/Library/Logs/Odysseus/`
- [ ] Data stored in `~/Library/Application Support/odysseus/`
- [ ] No Dock bounce loop; app groups correctly
- [ ] `build-mac-app.sh` runs cleanly from a fresh venv

---

## PR Filing Notes

- Depends on `feat/qt-native-linux-app` (issue #14) merged upstream first.
  If filing before: include shared JS files and note dependency.
- Reference upstream issue #606 (standalone native app request) and PR #3310
  (Electron wrapper): explain that Qt WebEngine uses the same Chromium engine
  as Electron but without bundling Node.js, using 35-50% less RAM, and
  integrating directly with the Python process.
- `build-mac-app.sh` is a new file; the existing `build-macos-app.sh` (Chrome
  --app mode) is separate and unmodified. Note the distinction in the PR.
- Must be tested on real macOS hardware before filing.
