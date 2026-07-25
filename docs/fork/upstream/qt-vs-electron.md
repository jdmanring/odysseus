# Qt WebEngine vs Electron: Technical Rationale

Both Qt WebEngine and Electron embed Chromium. The rendered output (CSS layout,
JavaScript execution, WebGPU, canvas, fonts) is identical. The difference is what
comes with the renderer.

## Memory Footprint

Electron starts a Chromium renderer and a Node.js process. Qt WebEngine starts only
the Chromium renderer, controlled by the Python process already running the server.
Measured idle consumption for a typical Electron app is
[100-300 MB](https://www.pythonguis.com/faq/html-css-and-js-in-a-desktop-app-qt-webengine-vs-electron-vs/);
Qt WebEngine carries no Node.js runtime overhead. On hardware running local AI models,
that gap competes with memory available for inference.

## No Bundled Node.js Runtime

Odysseus is a Python application. Electron ships Node.js so renderer processes can
import Node modules; none of that is needed here. Qt WebEngine has no equivalent:
the Python process is the only runtime, talking to the renderer via QWebChannel.

Electron's Node.js integration is also a documented attack surface. If
`nodeIntegration` or `contextIsolation` are misconfigured, renderer JavaScript can
reach the OS via Node.js APIs. Qt WebEngine has no such exposure.

## Disk Size

A packaged Electron app bundles Chromium and Node.js:
[approximately 46 MB on macOS, 97 MB on Windows](https://www.electronjs.org/docs/latest/tutorial/application-distribution)
before assets; real-world apps exceed 150 MB.

On Linux and FreeBSD, `qt6-qtwebengine` is a system package. The wrapper adds no
Chromium to disk; it is already installed as a dependency of other applications.
On Windows and macOS, only the Chromium engine downloads via pip (no Node.js).

## Direct Python Integration

Electron requires a separate Python process communicating via IPC, sockets, or local
HTTP. Qt WebEngine integrates directly: the Python process hosts the QApplication,
manages the QWebEngineView, and talks to the page via QWebChannel, no IPC layer.

## What This Wrapper Does That PR #3310 Does Not

Upstream PR #3310 opens a `BrowserWindow` pointed at a pre-running server. It does
not start, stop, or manage the server process.

This wrapper starts uvicorn before the window opens, kills stale server processes on
startup, and terminates the server cleanly on close. It maintains a persistent browser
profile: login survives restarts, where PR #3310 loses session on close. It handles
renderer crashes via `renderProcessTerminated` auto-reload. It provides a native color
picker via OS APIs and routes external links to the system browser.

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
system-installed engine.

---

## vs pywebview

pywebview uses the OS-provided webview on each platform: WKWebView on macOS,
WebView2 on Windows, WebKitGTK on Linux
([platform source](https://github.com/r0x0r/pywebview/tree/master/webview/platforms)).
On macOS and Windows, no Chromium binary ships with the app. The JS-to-Python bridge is
also genuinely cleaner: `window.pywebview.api.method()` returns a Promise directly,
no QWebChannel registration or signal/slot wiring.

The problem is platform coverage. There is no FreeBSD or OpenBSD support in pywebview.
An open issue tracking BSD ports has seen no progress for several years. Qt WebEngine
ships as a system package on both platforms (`pkg install qt6-qtwebengine` on FreeBSD,
`pkg_add qt6-qtwebengine` on OpenBSD).

The other problem is WebKitGTK rendering on LTS Linux. Ubuntu 22.04 shipped
WebKitGTK 2.36 in March 2022. Container queries landed in WebKit in September 2022,
six months later. WebGPU landed in October 2023. Users on 22.04 with pywebview
would be missing both, with no fix short of a system upgrade:

| Feature | Chromium (Qt WebEngine) | WebKitGTK 2.36 (Ubuntu 22.04¹) | WebKitGTK 2.44 (Ubuntu 24.04¹) |
|---------|------------------------|--------------------------------|--------------------------------|
| CSS Grid | ✓ Chrome 57 (2017) | ✓ | ✓ |
| `backdrop-filter` | ✓ Chrome 76 (2019) | `-webkit-` prefix only² | ✓ |
| Container queries | ✓ Chrome 105 (2022) | ✗ (landed WebKit Sept 2022³) | ✓ |
| WebGPU | ✓ Chrome 113 (2023) | ✗ (landed WebKit Oct 2023⁴) | Flagged only |

Sources: [caniuse.com: container queries](https://caniuse.com/css-container-queries),
[caniuse.com: WebGPU](https://caniuse.com/webgpu),
[packages.ubuntu.com](https://packages.ubuntu.com/search?keywords=libwebkit2gtk)

¹ Ubuntu ships security-updated packages on amd64; these version numbers reflect what
originally shipped. Non-amd64 architectures may remain at the original version.

² `-webkit-backdrop-filter` has been in WebKit since Safari 9 (2015); the unprefixed
property required a later WebKit version. WebKitGTK 2.36 shipped March 2022, prior
to widespread unprefixed support.

³ Container queries landed in Safari 16.0 (September 2022), six months after
WebKitGTK 2.36 shipped.

⁴ WebGPU landed in Safari 17.0 (October 2023, flagged); unflagged partial from
Safari 26 onwards. WebKitGTK 2.36 shipped 18 months before that.

Qt WebEngine bundles a current Chromium release and renders identically across all
five target platforms regardless of what the host OS ships.

There is also a documented threading issue: pywebview's webview and uvicorn both
compete for the main thread, with a history of blank-window-on-Windows startup
failures across minor version updates (see
[NiceGUI #2751](https://github.com/zauberzeug/nicegui/issues/2751)).

---

## vs Other Approaches

**cefpython3:** Python Chromium bindings, last release v66.1 (February 16, 2020),
targeting Chromium 66.0.3359.181. No Python 3.10+ support.
([releases](https://github.com/cztomczak/cefpython/releases))

**Tauri v2:** Rust framework using OS-provided webviews; same WebKitGTK tradeoffs
as pywebview on Linux. Python connects as a subprocess via Tauri's Shell plugin over
stdin/stdout or HTTP ([sidecar docs](https://v2.tauri.app/develop/sidecar/)). Odysseus
is Python. Shipping a Rust toolchain to get a desktop window is overhead with no payoff.
