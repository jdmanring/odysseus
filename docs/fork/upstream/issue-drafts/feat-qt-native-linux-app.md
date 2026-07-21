# Upstream Issue Draft: feat-qt-native-linux-app

**File on:** `odysseus-dev/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/feat-qt-native-linux-app.md`
**Branch:** `feat/qt-native-linux-app`
**Type:** Enhancement

**Related upstream discussions to reference:**
- #3309 — Electron desktop wrapper request
- #3609 — Community Electron wrapper discussion
- #3528 — Windows native desktop wrapper (parallel effort)

---

## Title

`[Linux] Native Linux desktop application wrapper (PyQt6 / QWebEngineView)`

---

## Body

**Area:** Platform / Desktop integration (Linux)

**Problem / Motivation:**
Odysseus runs in a browser tab on Linux. Users who want a standalone desktop experience — taskbar entry, desktop icon, Alt+Tab application, no browser chrome, no "close the wrong tab" accidents — have no supported path. Issue #3309 requests an Electron wrapper; discussion #3609 shows a working community Electron wrapper. However, Electron adds a full bundled Chromium binary (~200 MB) and a Node.js runtime to what is otherwise a pure Python application. On Linux, Qt WebEngine provides the same Chromium-based rendering engine via the distribution's existing Qt packages — no bundled browser binary required.

**Proposed Solution:**
An optional `qt_wrapper.py` entry point (PyQt6) and a `build-linux-app.sh` setup script. When launched via the script, Odysseus runs as a native desktop window:

- **Server lifecycle:** spawns `uvicorn app:app` as a subprocess, manages startup wait, kills it on window close
- **Persistent profile:** `QWebEngineProfile("odysseus")` with explicit data/cache paths in `~/.local/share/odysseus/webengine/` — cookies, `localStorage`, and `IndexedDB` survive across restarts (the default QWebEngineView profile is in-memory and loses all state on exit)
- **External links:** intercepts navigations targeting a new frame or new window and routes them to the system browser via `QDesktopServices.openUrl()`
- **Crash recovery:** `renderProcessTerminated` handler reloads the page on renderer OOM or crash, with a loop guard to prevent reload storms
- **Qt color picker bridge:** `QWebChannel` exposes `window.qtBridge` to the page; when the Web EyeDropper API is unavailable (it is not supported in QWebEngineView), the color picker falls back to the native Qt color dialog instead of staying permanently disabled
- **GPU flags:** sets safe Chromium flags for Linux/Wayland/NVIDIA — enables GPU rasterization and WebGPU, explicitly omits flags that cause blank windows on NVIDIA drivers on Linux

The wrapper is additive — no changes to the server, the web UI, or any existing functionality. Users who run Odysseus in a browser are entirely unaffected.

**Alternatives Considered:**
- **Electron (issue #3309 / discussion #3609):** Works and cross-platform, but adds a ~200 MB bundled Chromium binary and a Node.js runtime to a Python application. PyQt6-WebEngine achieves the same result on Linux using the distribution's Qt packages.
- **Tauri:** Well-reasoned recommendation in the architecture docs for a post-React-migration context. Not applicable here — this is a Python application with a plain HTML/JS frontend, and Tauri's Rust toolchain integration and native webview path are designed for a different architecture.
- **Browser shortcut / PWA:** No taskbar integration, no crash recovery, no native dialog bridging, no lifecycle management.
