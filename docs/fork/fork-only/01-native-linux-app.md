# [INTERNAL] Native Linux Application

## Description

Full native desktop integration for Odysseus on Linux. Runs the FastAPI backend in a venv
subprocess and wraps the web UI in a Qt native window with GPU acceleration, native Wayland
support, persistent login, and a JS-to-Python bridge for native OS capabilities.

## Key Components

- **`qt_wrapper.py`**: PyQt6/QWebEngineView wrapper; manages server lifecycle, GPU flags,
  persistent profile, QWebChannel bridge, zombie cleanup, and crash/signal handling.
- **`build-linux-app.sh`**: XDG-compliant install: launcher at `~/.local/bin/odysseus`, SVG
  icon at `~/.local/share/icons/hicolor/scalable/apps/odysseus.svg`, `.desktop` entry.
- **`static/js/qt-bridge.js`**: Non-module script; connects to QWebChannel and sets
  `window.qtBridge` so web JS can call native Qt APIs.
- **`docs/fork/build-linux-app.md`**: Full build and runtime reference.

## Architecture

Two separate Python runtimes:

| Layer | Runtime | Why |
|-------|---------|-----|
| Display (`qt_wrapper.py`) | `/usr/bin/python3` (system) | Needs system-built PyQt6 with Wayland support |
| Backend (`uvicorn app:app`) | `venv/bin/python` | All ML/server deps live in the venv |

**Do not use pip-distributed PyQt6 for the wrapper**; it is built without Wayland ozone support.

## GPU / Display Configuration

Qt auto-detects Wayland from `WAYLAND_DISPLAY`. The embedded Chromium renderer uses Vulkan
for GPU rendering (NVIDIA does not support GBM direct compositing in the QtWebEngine subprocess
context; this is an intentional Qt decision, not a misconfiguration).

Chromium flags set in `qt_wrapper.py`:
```
--no-sandbox                              required on Artix (user namespaces)
--ignore-gpu-blocklist                    override NVIDIA GPU blocklist
--enable-gpu-rasterization                GPU-accelerated 2D rendering
--enable-zero-copy                        zero-copy texture uploads
--enable-features=DefaultANGLEVulkan,     Vulkan backend for WebGL/Canvas via ANGLE
                  WebGPU,                 GPU compute for browser-side ML inference
                  SharedArrayBuffer       WASM-based ML workloads
```

Do NOT add `--ozone-platform=wayland`: it crashes on NVIDIA because the Chromium GPU subprocess
cannot access GBM directly. Qt handles Wayland natively without it.

## QWebChannel Bridge

`NativeBridge` (QObject) is registered on a `QWebChannel` and exposed to JS as `window.qtBridge`.
`window.__QT_WRAPPER__ = true` is injected at DocumentCreation so JS can detect the wrapper
synchronously. `qwebchannel.js` is injected from Qt's internal resources, no backend serving
needed. Both `QWebChannel` and `QtDBus` are bundled with `python-pyqt6`.

**Current bridge capabilities:**
- `openColorPicker()`: calls xdg-desktop-portal `PickColor` via `PyQt6.QtDBus`; native
  crosshair cursor, no intermediate dialog; falls back to `QColorDialog` if portal unavailable.

**Extending:** Add a `@pyqtSlot` method and signal to `NativeBridge` in `qt_wrapper.py`.

## Persistent Profile

Cookies, localStorage, and session data persist between restarts via named `QWebEngineProfile`:
- Data: `~/.local/share/odysseus/webengine/`
- Cache: `~/.cache/odysseus/webengine/`

## Status

- [x] Core implementation complete and verified on KDE/Artix (Wayland, NVIDIA RTX)
- [x] System PyQt6 (pacman): native Wayland Qt window
- [x] GPU acceleration via Vulkan (RTX 4070 Ti SUPER)
- [x] QWebChannel bridge with native color picker (xdg-desktop-portal)
- [x] WebGPU and SharedArrayBuffer enabled
- [x] Persistent login profile
- [x] KDE taskbar grouping and SVG icon
- [x] Zombie process cleanup and crash/signal handling
- [ ] AUR package (blocked pending build script stabilization)
- [ ] System tray + notification support (planned; requires QWebChannel extensions)

## Known Issues / Maintenance

See `docs/fork/runbooks/linux-maintenance.md` for operational notes including the
qt6-webengine version pin that must be removed when `python-pyqt6-webengine` updates to 6.11.1.
