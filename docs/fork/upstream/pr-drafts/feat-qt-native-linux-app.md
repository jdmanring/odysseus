# PR Draft: feat/qt-native-linux-app → pewdiepie-archdaemon/odysseus:dev

**Branch:** `jdmanring/odysseus:feat/qt-native-linux-app`
**Issue:** [#14](https://github.com/jdmanring/odysseus/issues/14) (fork tracking)
**Screenshot:** `docs/fork/screenshots/qt-native-linux-app.png`
**Status:** Ready to file


---

## Title

`feat(linux): native Linux desktop application (PyQt6 wrapper)`

---

## Summary

Adds an optional native Linux desktop wrapper that embeds the Odysseus web UI in
a `QWebEngineView` window. Users get a launcher/taskbar entry, desktop icon
integration, and a standalone app experience without needing a separate browser
tab. The Odysseus server runs in-process; the wrapper manages its full lifecycle.

<!-- Screenshot: drag `docs/fork/screenshots/qt-native-linux-app.png` into this text box when filing — the repo-relative path will not resolve upstream. -->

### New files

**`qt_wrapper.py`**: PyQt6 application entry point:

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
- **GPU flags:** sets `QTWEBENGINE_CHROMIUM_FLAGS` before importing Qt, with
  GPU vendor detection via `/proc/driver/nvidia`. Common flags: `--enable-gpu-rasterization`,
  `WebGPU`, `SharedArrayBuffer`, `--enable-logging=stderr`,
  `--remote-debugging-port=9222` (Chrome DevTools at `http://localhost:9222`).
  `DefaultANGLEVulkan` is absent for all configurations (forces ANGLE to Vulkan;
  causes blank/invisible windows on ozone/Wayland regardless of GPU vendor,
  Chromium bug 334275637). Vendor-conditional: **NVIDIA** (proprietary,
  `/proc/driver/nvidia` present) — `QTWEBENGINE_FORCE_USE_GBM=0` guards a Qt 6.9+
  regression (qutebrowser #8535) where Qt forces GBM on drivers that lack it;
  `--enable-zero-copy` is omitted (NVIDIA lacks GBM buffer allocation).
  **Mesa/AMD/Intel/Nouveau** (`/proc/driver/nvidia` absent) — `--enable-zero-copy`
  is enabled (native GBM buffer allocation path); no GBM guard needed.
  `setdefault` preserves any user override of the GBM env var.
- **Logging:** `os.dup2` redirects Chromium renderer fd 1/2 into
  `logs/wrapper_system.log` before Qt is imported so all renderer subprocess
  output is captured.

**`build-linux-app.sh`**: preflight check and launch script. Verifies that
`PyQt6`, `PyQt6-WebEngine`, and `PyQt6-sip` are importable, prints an install
hint if any are missing, then launches `qt_wrapper.py`. Dependencies must be
installed via the system package manager or `pip` before running the script
(distro packages vary; no cross-distro install path is guaranteed safe).

**`static/js/qt-bridge.js`**: injected into `QWebEngineView` at startup via
`QWebEngineScript`. Initialises `QWebChannel` and makes `window.qtBridge`
available to the rest of the JS codebase.

### Modified files

**`static/index.html`**: injects `qt-bridge.js` as a `<script>` tag so the
bridge initialises before any ES module code runs.

**`static/js/colorPicker.js`**: the Web EyeDropper API is unavailable inside
`QWebEngineView` (no OS-level pixel picker), leaving the eyedropper button
permanently disabled with "not supported in this browser". When
`window.__QT_WRAPPER__` is set, the eyedropper click instead calls
`window.qtBridge.openColorPicker()`, which opens the native Qt color dialog.
The selected hex value is returned via a `colorPicked` signal. Web EyeDropper
remains the path in regular browsers.

### Desktop wrapper approach: Qt over Electron or Tauri

This section documents the tradeoffs considered. Reviewers aware of upstream
issue #606 and PR #3310 will want to understand why Qt was chosen.

**The alternative landscape**

Issue #606 requests a standalone native application for Windows, Mac, and Linux.
PR #3310 is a community Electron wrapper that already works on Linux, Windows,
and macOS. Architecture document #605 explicitly recommends **Tauri** (not Electron)
and notes that a wrapper should follow the planned frontend migration to React/TypeScript.

**Why not Electron**

Electron ships its own full copy of Chromium (zipped apps run 80–100 MB and
exceed 100 MB unzipped, per [Electron's own documentation](https://www.electronjs.org/docs/latest/why-electron)). On Linux, this means installing and running a
second Chromium runtime alongside whatever browser the user already has. For a
Python application that already runs on the system, adding a Node.js + Electron
runtime stack purely for a desktop window is a heavy dependency with a
meaningful install cost.

PyQt6-WebEngine also uses a Chromium-based rendering engine (Qt WebEngine), so
there is no capability gap between the two approaches. The difference is that on
Linux, PyQt6-WebEngine can use the Qt WebEngine packages available from the
distribution's package manager; no bundled browser binary needed. The
PR #3310 works correctly but requires an `npm install electron` path that adds
this runtime overhead.

**Why not Tauri**

The architecture document's Tauri recommendation is well-reasoned for its
intended context: a post-React-migration frontend where Tauri's Rust toolchain
integration and native webview usage are appropriate.

Two reasons Tauri is not the right choice today:

1. **Rendering engine**: Tauri uses WebKitGTK on Linux. WebKitGTK feature availability depends on the
   version packaged by each distribution: Ubuntu 22.04 LTS ships WebKitGTK
   [2.36](https://launchpad.net/ubuntu/jammy/+source/webkit2gtk),
   which lacks `container queries`. Odysseus uses `backdrop-filter`,
   `grid`, `container queries`, and features whose behavior across the full
   range of distribution-packaged WebKitGTK versions is untested. Qt WebEngine
   is Chromium-based and renders identically to the browser regardless of
   distribution.

2. **Toolchain**: Odysseus has no Rust code and no Rust toolchain. Adding Tauri
   means adding a full Rust build environment as a mandatory dependency for a
   desktop wrapper. PyQt6 is a native Python binding; no new toolchain required.

When the React migration described in #605 is complete, revisiting Tauri may be
the right call. This PR does not conflict with that path; `qt_wrapper.py` is
optional and the server is unchanged.

**Why Qt is appropriate for Linux**

Qt is the standard native application toolkit on Linux distributions that use
KDE, and is a first-class citizen on GNOME via GTK interop. PyQt6 is available
from the package manager on Arch, Debian, Ubuntu, and Fedora. The GPU
acceleration flags in `qt_wrapper.py` are chosen specifically for
NVIDIA/Wayland compatibility: `--enable-gpu-rasterization` is safe and
effective; the Vulkan/GBM flags that are problematic on NVIDIA drivers on Linux
are explicitly absent. None of this is novel: PyQt6-WebEngine wrappers
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
venv; not added to `requirements.txt` (optional desktop feature, not needed
for server installs or Docker).

## Target branch

- [x] This PR targets **`dev`**, not `main`. All PRs land in `dev`; `main` is curated by the maintainer at each release.

## Linked Issue

Fixes #___

## Type of Change

- [ ] Bug fix (non-breaking, fixes a confirmed issue)
- [x] New feature (non-breaking, adds new behaviour)
- [ ] Breaking change (changes or removes existing behaviour)
- [ ] Refactor / cleanup (behaviour unchanged)
- [ ] Documentation only
- [ ] CI / tooling / configuration

## Checklist

- [x] I searched [open issues](https://github.com/pewdiepie-archdaemon/odysseus/issues) and [open PRs](https://github.com/pewdiepie-archdaemon/odysseus/pulls); this is not a duplicate.
- [x] This PR targets `dev`
- [x] My changes are limited to the scope described above; no unrelated refactors or whitespace changes mixed in.
- [x] I actually ran the app (`docker compose up` or `uvicorn app:app`) and verified the change works end-to-end. Type-checks and unit tests are not enough.

### How to Test

**Prerequisites:** Linux with PyQt6 and PyQt6-WebEngine available (or run `bash build-linux-app.sh` to install).

1. Run the wrapper: `bash build-linux-app.sh`: confirm it launches a native desktop window showing the Odysseus UI.
2. Log in; confirm login state persists after closing and re-opening the app (session stored in `~/.local/share/odysseus/webengine/`).
3. Click an external URL in an AI response; confirm it opens in the system browser, not inside the wrapper window.
4. Open Settings → Appearance → Theme and use the color picker; confirm the native Qt color dialog opens (not the browser eyedropper which is unsupported in QWebEngineView).
5. Open the sidebar, hover over items, open a dropdown, and open the Cookbook; confirm no black-screen flicker on any of these actions.
6. Chrome DevTools: navigate to `http://localhost:9222` in a regular browser; confirm the remote debugging endpoint is accessible.
7. Confirm standard features work: chat, session switching, model switching, Cookbook, Downloads, Settings.

Tested on: Artix Linux, Wayland, NVIDIA open drivers. Not tested on: macOS, Windows, touchscreen/tablet.

**Screenshots required:**
- Screenshot referenced in the description (`docs/fork/screenshots/qt-native-linux-app.png`) shows the app running with the color picker open. Attach via drag-and-drop in the GitHub PR form.

---

## Filing Notes

1. **File upstream issue first**: draft in `docs/fork/upstream/issue-drafts/feat-qt-native-linux-app.md`. Add the issue number to `Fixes #` above before opening the PR.
2. The screenshot in the description uses a repo-relative path. Attach the image directly in the GitHub PR text box via drag-and-drop; do not rely on the fork's file paths being visible to upstream reviewers.
3. Upstream issue #3528 (Windows desktop wrapper) shows the maintainer is receptive to native desktop wrappers. Reference it as a parallel effort in the issue or PR if asked about motivation.
4. Our fork issue #7 (HF token persistence) overlaps with upstream PR #3459. Monitor; if #3459 merges, verify after next sync whether the issue is fully resolved before filing separately.
5. **Port:** `qt_wrapper.py` now reads `APP_PORT` from the environment (`.env` is
   loaded automatically), defaulting to `7000` — the project's canonical upstream default
   (`docker-compose.yml`, `src/constants.py`, `launch-windows.ps1`). The previous
   hardcoded `8000` was a development artifact. No reviewer action needed; noted here for
   traceability.

## Visual / UI changes; REQUIRED if you touched anything that renders

- [x] Screenshot or short clip of the change in the running app, attached below. Mobile screenshot too if the change affects mobile layout.
- [x] Style match: the change uses Odysseus's existing visual language (existing CSS variables, button/card classes, no Unicode emoji, Fira Code font, dark-mode-first).
- [x] No new component patterns; extended an existing widget rather than adding a parallel one.
- [ ] **I am not an LLM agent submitting a bulk PR.** I reviewed and tested this change personally before submitting.

### Screenshots / clips

<!-- Attach screenshots by dragging and dropping into this text box. -->
