# Implementation Plan: macOS Native Wrapper

**Fork issue:** [#43](https://github.com/jdmanring/odysseus/issues/43)
**Branch origin:** `upstream-mirror` (upstream-candidate)
**Branch name:** `feat/qt-native-macos-app`
**Depends on:** Issue #14 / `feat/qt-native-linux-app` merged upstream first (shared JS bridge files)

---

## Overview

Create `mac_wrapper.py` and `build-mac-app.sh` — a native macOS desktop wrapper using
PyQt6, modeled directly on `linux_wrapper.py`. The architecture is identical; only the
platform-specific blocks differ.

---

## Files to Create

### `mac_wrapper.py`

Start from `linux_wrapper.py` and apply the following changes:

**1. LOG_DIR** — change log location to macOS convention:
```python
LOG_DIR = os.path.join(os.path.expanduser("~"), "Library", "Logs", "Odysseus")
```

**2. Remove `QTWEBENGINE_FORCE_USE_GBM`** — this guards a Qt 6.9+ Linux regression;
not applicable on macOS:
```python
# Remove this line entirely:
os.environ.setdefault("QTWEBENGINE_FORCE_USE_GBM", "0")
```

**3. Chromium flags** — replace the Linux flag block with macOS-appropriate flags.
macOS uses Metal natively; no GBM/Vulkan guards needed:
```python
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
    "--ignore-gpu-blocklist "
    "--enable-gpu-rasterization "
    "--enable-features=WebGPU,SharedArrayBuffer "
    "--enable-logging=stderr --log-level=1 "
    "--remote-debugging-port=9222"
)
```
Flags removed vs Linux: `--no-sandbox` (not required on macOS), all Vulkan/GBM guards.

**4. Imports** — remove D-Bus imports (not available on macOS):
```python
# Remove:
from PyQt6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage
```

**5. PORT default** — use 7860 (AirPlay Receiver holds 7000 on macOS):
```python
PORT = os.environ.get("APP_PORT", "7860")
```

**6. NativeBridge** — replace the D-Bus portal path with direct `QColorDialog`:
```python
class NativeBridge(QObject):
    colorPicked = pyqtSignal(str)

    @pyqtSlot()
    def openColorPicker(self):
        color = QColorDialog.getColor()
        self.colorPicked.emit(color.name() if color.isValid() else '')
```
The entire `_on_response` and `_fallback` infrastructure from the Linux version is
replaced by this single method.

**7. `_log_renderer_memory()`** — `pgrep` works on macOS; no change needed.

**8. `app.setDesktopFileName()`** — not available on macOS. Replace with:
```python
app.setApplicationName("Odysseus")
app.setOrganizationName("Odysseus")
```
These populate macOS bundle metadata and `NSUserDefaults` domain.

**9. QSettings** — no change. Qt automatically writes to `~/Library/Preferences/` on
macOS when using `QSettings("odysseus", "odysseus")`.

**10. VENV_PYTHON** — same as Linux (`venv/bin/python`); correct on macOS.

### `build-mac-app.sh`

```bash
#!/bin/bash
set -e
cd "$(dirname "$0")"
python3 -m venv venv
venv/bin/pip install --quiet PyQt6 PyQt6-WebEngine PyQt6-sip
exec venv/bin/python mac_wrapper.py "$@"
```

---

## Files Already Present (no changes needed)

These were added by `feat/qt-native-linux-app` and work on macOS without modification:

- `static/js/qt-bridge.js` — `window.__QT_WRAPPER__` guard is platform-neutral
- `static/index.html` — `<script>` injection is platform-neutral
- `static/js/colorPicker.js` — `window.qtBridge.openColorPicker()` call is neutral;
  the native dialog implementation differs (macOS uses `QColorDialog` directly)

---

## Implementation Steps

1. `git checkout upstream-mirror && git checkout -b feat/qt-native-macos-app`
2. Create `mac_wrapper.py` per the spec above
3. Create `build-mac-app.sh` and `chmod +x build-mac-app.sh`
4. Run `bash build-mac-app.sh` on a macOS machine; verify the window appears
5. Test: login state persists across restarts; external links open in system browser;
   color picker opens native dialog; window size/maximized state restores
6. Verify port: confirm `ps aux | grep uvicorn` shows `--port 7860`
7. Verify logs appear in `~/Library/Logs/Odysseus/`
8. Screenshot the running app for the PR
9. Write PR draft at `docs/fork/upstream/pr-drafts/feat-qt-native-macos-app.md`
   (model it on `feat-qt-native-linux-app.md`; reference issue #43 and upstream #3528)
10. Cherry-pick to `develop`; mark issue #43 in-progress

---

## Testing Checklist

- [ ] App launches; Odysseus UI loads in a native macOS window
- [ ] Server starts on port 7860; no port conflict with AirPlay Receiver
- [ ] Login persists after closing and reopening
- [ ] External link opens in system browser (Safari/Chrome), not inside the wrapper
- [ ] Color picker opens `QColorDialog` (no crash, no silent fail)
- [ ] Window size and maximized state restore correctly on reopen
- [ ] Chrome DevTools available at `http://localhost:9222`
- [ ] Logs appear in `~/Library/Logs/Odysseus/`
- [ ] No Dock bounce loop on start; app groups correctly in Dock
- [ ] `build-mac-app.sh` runs cleanly from a fresh clone (no pre-existing venv)

---

## PR Filing Notes

- Depends on `feat/qt-native-linux-app` (issue #14) being merged upstream first.
  The shared JS files (`qt-bridge.js`, `index.html` changes, `colorPicker.js`)
  are introduced there; this PR adds only `mac_wrapper.py` and `build-mac-app.sh`.
- If filing before #14 merges: include the shared JS files in this PR and note the
  dependency in the description.
- Reference upstream issue #3528 (Windows desktop wrapper) and issue #14's PR as
  prior art.
- Must be tested on a real macOS machine before filing. PyQt6 on macOS requires
  Xcode command line tools; `build-mac-app.sh` handles the rest.
