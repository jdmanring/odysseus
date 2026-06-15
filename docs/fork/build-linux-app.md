# Building the Linux App (Fork)

## Architecture

The Linux native app has two separate Python runtimes:

| Layer | Python | Why |
|-------|--------|-----|
| Display (`qt_wrapper.py`) | `/usr/bin/python3` (system) | Uses system-built PyQt6/WebEngine with native Wayland support |
| Backend (`uvicorn app:app`) | `venv/bin/python` | All server dependencies (FastAPI, ML libs, etc.) live in the venv |

The pip-distributed PyQt6 must not be used for the wrapper — use system packages only.

## Prerequisites

### System packages (pacman)
```bash
sudo pacman -S python-pyqt6 python-pyqt6-webengine
```

Qt itself runs on native Wayland. The embedded Chromium renderer uses Vulkan for GPU rendering (NVIDIA does not support GBM direct compositing in the QtWebEngine subprocess). The pip equivalents (`PyQt6`, `PyQt6-WebEngine`) must not be installed in the venv — remove them if present:
```bash
venv/bin/python -m pip uninstall -y PyQt6 PyQt6-Qt6 PyQt6_sip PyQt6-WebEngine PyQt6-WebEngine-Qt6
```

### Version pinning
`qt6-webengine` must match `python-pyqt6-webengine`. If a system update upgrades one without the other, the app will crash at startup. Pin `qt6-webengine` in `/etc/pacman.conf` until both are in sync:
```
IgnorePkg = qt6-webengine
```

### Venv (server deps only)
```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

## Install

```bash
bash build-linux-app.sh
```

The script:
1. Verifies system PyQt6 with WebEngine is available
2. Installs the launcher at `~/.local/bin/odysseus` (uses `/usr/bin/python3`)
3. Installs `static/icons/odysseus.svg` to the hicolor scalable icon directory
4. Writes the `.desktop` entry and refreshes icon/desktop caches

Log out and back in after the first install so KDE picks up the new icon.

## Runtime configuration

### Chromium flags (`qt_wrapper.py`)
```
--no-sandbox                              required on Artix (user namespaces may not be enabled)
--ignore-gpu-blocklist                    override Chromium's NVIDIA GPU feature blocklist
--enable-gpu-rasterization                GPU-accelerated 2D rendering
--enable-zero-copy                        zero-copy texture uploads to GPU
--enable-features=DefaultANGLEVulkan,     Vulkan backend for WebGL/Canvas via ANGLE;
                  WebGPU,                 GPU compute for browser-side ML inference
                  SharedArrayBuffer       required for WASM-based ML workloads
```

Qt auto-detects Wayland from `WAYLAND_DISPLAY` — no `QT_QPA_PLATFORM` override needed.
Do not add `--ozone-platform=wayland` — that flag is for standalone Chromium, not QtWebEngine.
On NVIDIA, Chromium falls back to Vulkan rendering (GBM direct compositing is unavailable in the
subprocess context). Full GPU acceleration is still active via the RTX.

### Qt native bridge (QWebChannel)

`qt_wrapper.py` exposes a `NativeBridge` QObject to JavaScript via `window.qtBridge`. It is
available in the page after the QWebChannel handshake completes (async, always done before any
user interaction). The `window.__QT_WRAPPER__` flag is set synchronously at document creation so
JS can detect the wrapper environment immediately.

**Color picker (`static/js/colorPicker.js`)**
The eyedropper button uses the xdg-desktop-portal `PickColor` API (same mechanism as the
browser EyeDropper API on Linux) — no intermediate dialog. The portal call is made via
`PyQt6.QtDBus`; the crosshair cursor is provided by the KDE portal implementation. Falls back
to `QColorDialog` if the portal is unavailable.

**Extending the bridge**
Add a `@pyqtSlot` method to `NativeBridge` and a corresponding signal. Register no additional
packages — `QWebChannel` and `QtDBus` are bundled with `python-pyqt6`.

### Log files
All logs go to `$REPO/logs/`:
- `wrapper_system.log` — Python wrapper stdout/stderr
- `server.log` — uvicorn/FastAPI (via `ODYSSEUS_LOG_FILE` env var)
- `chrome_debug.log` — Chromium renderer

### Persistent profile
Browser storage (cookies, localStorage, session) lives at:
- `~/.local/share/odysseus/webengine/` — persistent data
- `~/.cache/odysseus/webengine/` — network/GPU cache
