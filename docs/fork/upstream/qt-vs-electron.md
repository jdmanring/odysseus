# Qt WebEngine vs Electron: Technical Rationale

This document backs the argument made in the native wrapper PR series
(`feat/qt-native-linux-app`, `feat/qt-native-macos-app`, etc.) that Qt WebEngine
is a better fit for Odysseus than Electron (upstream PR #3310, issue #606).

---

## Same Rendering Engine

Both Qt WebEngine and Electron embed Chromium. The rendered output — CSS layout,
JavaScript execution, WebGPU, canvas, fonts — is identical. Choosing Electron over
Qt WebEngine buys no improvement in what the browser renders.

---

## Memory Footprint

Electron starts a full Chromium renderer **and** a Node.js process. Qt WebEngine
starts only the Chromium renderer, controlled by the Python process already running
the server.

A typical Electron application uses **100–300 MB at idle** (source:
[pythonguis.com — HTML/CSS/JS in a desktop app: Qt WebEngine vs Electron](https://www.pythonguis.com/faq/html-css-and-js-in-a-desktop-app-qt-webengine-vs-electron-vs/)).
Qt WebEngine carries no Node.js runtime and no separate renderer process manager,
making its idle footprint structurally lower. On constrained hardware — ARM SBCs,
tablet-class Linux devices, machines running local AI models — this difference
directly competes with memory available for inference.

---

## No Bundled Node.js Runtime

Electron ships Node.js alongside Chromium so that renderer processes can import
Node.js modules. Odysseus is a Python application. There is no reason to ship a
Node.js runtime. Qt WebEngine has no equivalent — the Python process is the only
runtime, communicating with the Chromium renderer via QWebChannel.

Electron's Node.js integration is also a documented security surface. If
`nodeIntegration` or `contextIsolation` settings are misconfigured, renderer
JavaScript can reach the OS via Node.js APIs. Qt WebEngine has no such exposure.

---

## Disk Size

A minimal packaged Electron application bundles Chromium and Node.js into the
distributable. Electron's own documentation notes the minimum app size after
packaging is approximately 46 MB on macOS and 97 MB on Windows before assets
(source: [Electron — Application Distribution](https://www.electronjs.org/docs/latest/tutorial/application-distribution));
real-world apps with assets routinely exceed 150 MB.

On Linux and FreeBSD where Qt WebEngine is a system package, the wrapper adds zero
disk overhead for the Chromium engine — it is already installed as a dependency of
other applications. On Windows and macOS where PyQt6 is installed via pip, only
the Chromium engine is downloaded (no Node.js).

---

## Direct Python Integration

Electron requires a separate Python process communicating with the renderer via IPC,
sockets, or local HTTP — adding complexity and latency. Qt WebEngine integrates
directly: the Python process hosts the QApplication, manages the QWebEngineView, and
communicates with the page via QWebChannel with no IPC layer.

---

## What This Wrapper Does That Upstream PR #3310 Does Not

Upstream PR #3310 (Electron wrapper) opens a `BrowserWindow` pointed at a
**pre-running** server. It does not start, stop, or manage the server process.

This wrapper:

- Starts the uvicorn server as a subprocess before the window opens
- Kills stale server processes on startup (zombie prevention)
- Manages the server PID and terminates it cleanly on window close
- Handles crash recovery: `renderProcessTerminated` auto-reloads on OOM or hard crash
- Maintains a named, isolated persistent profile (login survives across restarts;
  PR #3310 uses no persistent profile — login is lost on restart)
- Routes external links to the system browser (not a new tab in the wrapper)
- Persists window size and maximized state across restarts
- Provides a native color picker via OS APIs (D-Bus portal on Linux/FreeBSD,
  QColorDialog on macOS/Windows/OpenBSD)
- Exposes Chrome DevTools on `:9222` for debugging
- Logs renderer stdout/stderr alongside server logs in a unified log directory

---

## Platform Coverage

| Platform | Qt WebEngine status |
|----------|-------------------|
| Linux | System package on all major distros |
| macOS | Via pip (`PyQt6-WebEngine`) |
| Windows | Via pip (`PyQt6-WebEngine`) |
| FreeBSD | `pkg install qt6-qtwebengine` |
| OpenBSD | `pkg_add qt6-qtwebengine` (amd64/aarch64 only) |

Electron has equivalent cross-platform reach, but every platform requires bundling
Node.js and a full Chromium binary. Qt WebEngine on Linux and FreeBSD reuses the
system-installed Chromium engine.

---

## vs pywebview (System Webview Approach)

pywebview (v6.2.1, released April 2026; source:
[github.com/r0x0r/pywebview](https://github.com/r0x0r/pywebview/releases)) is the
closest Python-native alternative. It uses the OS-provided webview on each platform:
WKWebView on macOS, WebView2 on Windows, and WebKitGTK on Linux (verified from
[platform source files](https://github.com/r0x0r/pywebview/tree/master/webview/platforms)).
No bundled Chromium — structurally smaller process footprint.

**Where pywebview is stronger:**

- **JS↔Python bridge:** pywebview exposes a Python class directly to JS via
  `window.pywebview.api.method()`, which returns a Promise. No QWebChannel
  registration, no signal/slot wiring — tighter for Python-from-JS calls.
- **Memory:** No bundled Chromium renderer process; no published head-to-head
  measurement was found, but the structural overhead is lower on macOS and Windows.

**Why Qt WebEngine is the right choice for Odysseus:**

**1. Platform coverage.** pywebview has no FreeBSD or OpenBSD support. An open
issue tracking BSD support has seen no progress for several years. Qt WebEngine is
available as a system package on both platforms — `pkg install qt6-qtwebengine` on
FreeBSD, `pkg_add qt6-qtwebengine` on OpenBSD amd64/aarch64. Supporting BSD
targets without maintaining pywebview ports ourselves is only possible with Qt
WebEngine.

**2. Rendering consistency.** pywebview on Linux uses WebKitGTK, which is packaged
independently per distribution. The rendering gap against Qt WebEngine's bundled
Chromium is visible in the release timeline:

| Feature | Chromium (Qt WebEngine) | WebKitGTK 2.36 (Ubuntu 22.04 as shipped¹) | WebKitGTK 2.44 (Ubuntu 24.04 as shipped¹) |
|---------|------------------------|-------------------------------------------|-------------------------------------------|
| CSS Grid | ✓ Chrome 57 (2017) | ✓ | ✓ |
| `backdrop-filter` | ✓ Chrome 76 (2019) | `-webkit-` prefix only² | ✓ (unprefixed in WebKit 2024) |
| Container queries | ✓ Chrome 105 (2022) | ✗ (landed in WebKit Sept 2022³) | ✓ |
| WebGPU | ✓ Chrome 113 (2023) | ✗ (landed in WebKit Oct 2023⁴) | Flagged only |

Sources:
[caniuse.com — CSS container queries](https://caniuse.com/css-container-queries),
[caniuse.com — backdrop-filter](https://caniuse.com/css-backdrop-filter),
[caniuse.com — WebGPU](https://caniuse.com/webgpu)

¹ Ubuntu ships security-updated packages on amd64; these version numbers reflect
what originally shipped. Non-amd64 architectures may remain at the original version.
([packages.ubuntu.com](https://packages.ubuntu.com/search?keywords=libwebkit2gtk))

² `-webkit-backdrop-filter` has been in WebKit since Safari 9 (2015); the unprefixed
property required a significantly later WebKit version. WebKitGTK 2.36 shipped
March 2022, prior to widespread unprefixed support.

³ Container queries landed in Safari 16.0 (September 2022) — six months after
WebKitGTK 2.36 shipped.

⁴ WebGPU landed in WebKit in Safari 17.0 (October 2023, flagged) and is
unflagged partial only from Safari 26 onwards (source: caniuse.com/webgpu).
WebKitGTK 2.36 shipped 18 months before the Safari 17 flag was introduced.

Qt WebEngine bundles a current Chromium release and renders identically across
all five target platforms regardless of what the host OS ships.

**3. Threading.** pywebview's webview and uvicorn both require the main thread.
This requires careful coordination and has a documented history of
blank-window-on-Windows and startup failures across pywebview minor version
updates (see [NiceGUI issue #2751](https://github.com/zauberzeug/nicegui/issues/2751),
which documents `ui.run(native=True)` producing a blank window on Windows 11 despite
the server starting successfully). Qt WebEngine's event loop owns the main thread
cleanly; the uvicorn subprocess runs separately with no contention.

---

## vs Other Approaches

**cefpython3:** Python bindings for Chromium Embedded Framework. Last release:
v66.1, released February 16, 2020, targeting Chromium 66.0.3359.181. No Python
3.10+ support. Not maintained; not viable.
(Source: [github.com/cztomczak/cefpython/releases](https://github.com/cztomczak/cefpython/releases))

**Tauri v2:** Rust framework using OS-provided webviews (same rendering tradeoffs
as pywebview). Python integration uses the Sidecar pattern — the Python server runs
as a separate subprocess spawned by Tauri's Shell plugin, communicating via
stdin/stdout or HTTP. There is no same-process Python integration.
(Source: [v2.tauri.app/develop/sidecar](https://v2.tauri.app/develop/sidecar/))
Adding a full Rust toolchain to the build pipeline for a Python-primary application
introduces significant maintenance cost with no functional benefit over Qt WebEngine.
Tauri is the right choice when Rust is the primary runtime; it is the wrong choice here.

**Summary:** For a Python-first application targeting Linux, macOS, Windows,
FreeBSD, and OpenBSD with a Chromium-based frontend, Qt WebEngine is the correct
choice. pywebview would be reasonable on macOS and Windows only, where BSD support
and WebKitGTK rendering gaps are not a concern.
