# PR Draft: feat/qt-native-linux-app-rebuild → pewdiepie-archdaemon/odysseus:dev

**Branch:** `jdmanring/odysseus:feat/qt-native-linux-app-rebuild`
**Issue:** [#14](https://github.com/jdmanring/odysseus/issues/14) (fork tracking)
**Screenshot:** `docs/fork/screenshots/qt-native-linux-app.png`
**Status:** Ready to file

Note: Use `feat/qt-native-linux-app-rebuild`, not `feat/qt-native-linux-app`.
The rebuild branch is clean (1 commit, 5 files). The original branch accumulated
unrelated history and should not be filed.

---

## Title

`feat(linux): native Linux desktop application (PyQt6 wrapper)`

---

## Description

### Summary

Adds an optional native Linux desktop wrapper that embeds the Odysseus web UI in
a `QWebEngineView` window. Users get a launcher/taskbar entry, desktop icon
integration, and a standalone app experience without needing a separate browser
tab. The Odysseus server runs in-process; the wrapper manages its full lifecycle.

![Odysseus running as a native Linux desktop app with the theme/color picker open](docs/fork/screenshots/qt-native-linux-app.png)

### New files

**`linux_wrapper.py`** — PyQt6 application entry point:

- **Server lifecycle:** spawns `uvicorn app:app` as a subprocess on startup,
  kills it on window close. Waits up to 30 s for the server to become ready
  before loading the UI.
- **Persistent profile:** uses `QWebEngineProfile("odysseus")` with explicit
  data/cache paths in `~/.local/share/odysseus/webengine/` and
  `~/.cache/odysseus/webengine/`. Cookies, `localStorage`, and `IndexedDB`
  survive across restarts (default `QWebEngineView` uses an in-memory profile
  that wipes everything on exit).
- **External links:** `OdysseusPage(QWebEnginePage)` subclass intercepts
  navigations targeting a new frame (`navigationRequested` with
  `NavigationType.Link` + `isMainFrame=False` or a new-window request) and
  routes them to `QDesktopServices.openUrl()` so external links open in the
  system browser instead of navigating away inside the wrapper.
- **Crash recovery:** `renderProcessTerminated` handler reloads the page on
  OOM or renderer crash, with a loop guard to avoid reload storms.
- **Memory monitor:** `QTimer`-driven 60 s loop logs renderer heap usage via
  `runJavaScript` for diagnostics.
- **Qt bridge:** `QWebChannel` exposes `window.qtBridge` to the page for
  features that require a native dialog.
- **GPU flags:** sets `QTWEBENGINE_CHROMIUM_FLAGS` before importing Qt to
  enable GPU rasterization, Vulkan/ANGLE, WebGPU, and zero-copy transfer on
  NVIDIA/Wayland setups.
- **Logging:** `os.dup2` redirects Chromium renderer fd 1/2 into
  `logs/wrapper_system.log` before Qt is imported so all renderer subprocess
  output is captured.

**`build-linux-app.sh`** — dependency installation and launch script. Installs
`PyQt6`, `PyQt6-WebEngine`, and `PyQt6-sip` into the project venv, then
launches `linux_wrapper.py`.

**`static/js/qt-bridge.js`** — injected into `QWebEngineView` at startup via
`QWebEngineScript`. Initialises `QWebChannel` and makes `window.qtBridge`
available to the rest of the JS codebase.

### Modified files

**`static/index.html`** — injects `qt-bridge.js` as a `<script>` tag so the
bridge initialises before any ES module code runs.

**`static/js/colorPicker.js`** — the Web EyeDropper API is unavailable inside
`QWebEngineView` (no OS-level pixel picker), leaving the eyedropper button
permanently disabled with "not supported in this browser". When
`window.__QT_WRAPPER__` is set, the eyedropper click instead calls
`window.qtBridge.openColorPicker()`, which opens the native Qt color dialog.
The selected hex value is returned via a `colorPicked` signal. Web EyeDropper
remains the path in regular browsers.

### No changes to server, API, or non-Qt JS paths

All changes are either new files or guarded behind `window.__QT_WRAPPER__` /
`window.qtBridge` checks. The wrapper has zero effect on Docker, native, or
browser installs.

### Dependencies

PyQt6, PyQt6-WebEngine. Installed by `build-linux-app.sh` into the existing
venv — not added to `requirements.txt` (optional desktop feature, not needed
for server installs or Docker).

### Testing

- Arch Linux, Wayland, NVIDIA GPU.
- Session persistence verified: login state, theme, and session history survive
  app restart.
- External links (URLs in AI responses, markdown links) open in the system
  browser.
- Renderer crash recovery: page reloads once on OOM without a reload loop.
- Color picker: native Qt dialog opens, returns hex, closes; eyedropper button
  hidden if `qtBridge` is unavailable.

---

## Filing Notes (James)

1. File issue on `pewdiepie-archdaemon/odysseus` first; add its number here
   before opening the PR.
2. Use branch `feat/qt-native-linux-app-rebuild`, not `feat/qt-native-linux-app`.
3. The screenshot path in the description above uses the repo-relative path.
   Attach the image directly in the GitHub PR description instead (drag and
   drop into the text box) — GitHub renders it inline and it won't depend on
   the fork's file structure being visible to upstream reviewers.
4. Upstream issue #3528 (Windows desktop) shows the maintainer is receptive to
   native desktop wrappers. Reference it as a parallel effort if asked about
   motivation.
5. Our #7 (HF token persistence) overlaps with upstream PR #3459, which fixes
   a related token detection bug. Monitor — if #3459 merges, check whether our
   issue is fully resolved after next sync before filing separately.
