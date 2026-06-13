# PR Draft: feat/qt-native-linux-app → pewdiepie-archdaemon/odysseus:dev

**Branch:** `jdmanring/odysseus:feat/qt-native-linux-app`
**Issue:** [#14](https://github.com/jdmanring/odysseus/issues/14) (fork tracking)
**Screenshot:** `docs/fork/screenshots/qt-native-linux-app.png`
**Status:** Ready to file


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
- **GPU flags:** sets `QTWEBENGINE_CHROMIUM_FLAGS` and
  `QTWEBENGINE_FORCE_USE_GBM` before importing Qt. Flags enabled:
  `--enable-gpu-rasterization` (GPU tile rasterisation — safe on NVIDIA Linux),
  `WebGPU`, `SharedArrayBuffer`, `--enable-logging=stderr`,
  `--remote-debugging-port=9222` (Chrome DevTools at `http://localhost:9222`
  for GPU compositor layer inspection). Flags explicitly absent: `DefaultANGLEVulkan`
  (forces ANGLE to Vulkan — documented to cause blank/invisible windows on
  ozone/Wayland, Chromium bug 334275637) and `--enable-zero-copy` (requires
  GBM buffer allocation, which NVIDIA proprietary drivers don't support — Qt
  WebEngine 6.6 release notes; was a no-op and a source of texture-sharing
  failures). `QTWEBENGINE_FORCE_USE_GBM=0` guards against a Qt 6.9+ regression
  (qutebrowser #8535) where Qt incorrectly forces GBM on drivers that don't
  support it; `setdefault` preserves any user override.
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

### Desktop wrapper approach: Qt over Electron or Tauri

This section documents the tradeoffs considered. Reviewers aware of upstream
issue #3309 and discussion #3609 will want to understand why Qt was chosen.

**The alternative landscape**

Issue #3309 requests an Electron-based desktop wrapper. Discussion #3609 shows
a community Electron wrapper that already works on Linux, Windows, and macOS.
Architecture document #605 explicitly recommends **Tauri** (not Electron) and
notes that a wrapper should follow the planned frontend migration to
React/TypeScript.

**Why not Electron**

Electron ships its own full copy of Chromium (~200 MB on disk, ~100–200 MB
additional RAM per process). On Linux, this means installing and running a
second Chromium runtime alongside whatever browser the user already has. For a
Python application that already runs on the system, adding a Node.js + Electron
runtime stack purely for a desktop window is a heavy dependency with a
meaningful install cost.

PyQt6-WebEngine also uses a Chromium-based rendering engine (Qt WebEngine), so
there is no capability gap between the two approaches. The difference is that on
Linux, PyQt6-WebEngine can use the Qt WebEngine packages available from the
distribution's package manager — no bundled browser binary needed. The
community wrapper in discussion #3609 works correctly but requires an
`npm install electron` path that adds this runtime overhead.

**Why not Tauri**

The architecture document's Tauri recommendation is well-reasoned for its
intended context: a post-React-migration frontend where Tauri's Rust toolchain
integration and native webview usage are appropriate.

Two reasons Tauri is not the right choice today:

1. **Rendering engine**: Tauri uses WebKitGTK on Linux. WebKitGTK trails
   Blink/Chrome in CSS and web platform feature support. Odysseus uses
   `backdrop-filter`, `grid`, `container queries`, and progressive rendering
   features that work on Chrome. Whether they work on the version of WebKitGTK
   present on a given Linux distribution is untested and risky. Qt WebEngine
   is Chromium-based and renders identically to the browser.

2. **Toolchain**: Odysseus has no Rust code and no Rust toolchain. Adding Tauri
   means adding a full Rust build environment as a mandatory dependency for a
   desktop wrapper. PyQt6 is a native Python binding — no new toolchain required.

When the React migration described in #605 is complete, revisiting Tauri may be
the right call. This PR does not conflict with that path; `linux_wrapper.py` is
optional and the server is unchanged.

**Why Qt is appropriate for Linux**

Qt is the standard native application toolkit on Linux distributions that use
KDE, and is a first-class citizen on GNOME via GTK interop. PyQt6 is available
from the package manager on Arch, Debian, Ubuntu, and Fedora. The GPU
acceleration flags in `linux_wrapper.py` are chosen specifically for
NVIDIA/Wayland compatibility: `--enable-gpu-rasterization` is safe and
effective; the Vulkan/GBM flags that are problematic on NVIDIA proprietary
drivers are explicitly absent. None of this is novel: PyQt6-WebEngine wrappers
are a well-understood pattern for Python web apps that need a desktop presence
on Linux.

This PR does not attempt to cover Windows or macOS. Issue #3528 addresses a
Windows desktop mode separately. Cross-platform coverage via Electron or Tauri
is a reasonable follow-up; this PR delivers the Linux case using the tooling
that is already on every Linux machine in the target audience.

### No changes to server, API, or non-Qt JS paths

All changes are either new files or guarded behind `window.__QT_WRAPPER__` /
`window.qtBridge` checks. The wrapper has zero effect on Docker, native, or
browser installs.

### Dependencies

PyQt6, PyQt6-WebEngine. Installed by `build-linux-app.sh` into the existing
venv — not added to `requirements.txt` (optional desktop feature, not needed
for server installs or Docker).

### How to Test

**Prerequisites:** Linux with PyQt6 and PyQt6-WebEngine available (or run `bash build-linux-app.sh` to install).

1. Run the wrapper: `bash build-linux-app.sh` — confirm it launches a native desktop window showing the Odysseus UI.
2. Log in; confirm login state persists after closing and re-opening the app (session stored in `~/.local/share/odysseus/webengine/`).
3. Click an external URL in an AI response — confirm it opens in the system browser, not inside the wrapper window.
4. Open Settings → Appearance → Theme and use the color picker — confirm the native Qt color dialog opens (not the browser eyedropper which is unsupported in QWebEngineView).
5. Open the sidebar, hover over items, open a dropdown, and open the Cookbook — confirm no black-screen flicker on any of these actions.
6. Chrome DevTools: navigate to `http://localhost:9222` in a regular browser — confirm the remote debugging endpoint is accessible.
7. Confirm standard features work: chat, session switching, model switching, Cookbook, Downloads, Settings.

Tested on: Arch Linux, Wayland, NVIDIA GPU (proprietary drivers). Not tested on: macOS, Windows, touchscreen/tablet.

**Screenshots required:**
- Screenshot referenced in the description (`docs/fork/screenshots/qt-native-linux-app.png`) shows the app running with the color picker open. Attach via drag-and-drop in the GitHub PR form.

---

## Filing Notes (James)

1. File issue on `pewdiepie-archdaemon/odysseus` first; add its number here
   before opening the PR.
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
