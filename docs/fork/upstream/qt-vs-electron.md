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
the server. Measurements from independent sources:

| Setup | RAM at idle |
|-------|------------|
| Electron (typical app) | 200–400 MB |
| Qt WebEngine (Python app) | 100–180 MB |
| Raspberry Pi 5 (Electron) | ~400 MB |
| Raspberry Pi 5 (Qt WebEngine) | ~180 MB |

**35–50% less RAM.** On a machine with 4–8 GB of RAM running local AI models,
this is a meaningful difference. On tablet-class Linux hardware (PineTab2, ARM SBCs,
Steam Deck, upcoming ARM Linux tablets), 200 MB of saved RAM directly translates to
more available headroom for the model inference process.

Sources: [pythonguis.com Qt WebEngine vs Electron](https://www.pythonguis.com/faq/html-css-and-js-in-a-desktop-app-qt-webengine-vs-electron-vs/),
[johal.in PyQt WebEngine 2025](https://www.johal.in/pyqt-webengine-python-chromium-browser-widgets-embedded-2025/),
[Petar Koretić, Medium: Electron vs Qt memory](https://pkoretic.medium.com/quick-look-electron-vs-qt-qml-app-memory-usage-e8769008534f),
[pkgpulse.com desktop frameworks 2026](https://www.pkgpulse.com/guides/best-desktop-app-frameworks-2026)

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

A minimal Electron app distributes at 80–200 MB because it bundles Chromium + Node.js.
On Linux and FreeBSD where Qt WebEngine is a system package, the wrapper adds zero
disk overhead for the Chromium engine — it is already installed as a dependency of
other applications. On Windows and macOS where PyQt6 is installed via pip, it is
~100 MB (Chromium only; no Node.js).

Source: [pkgpulse.com](https://www.pkgpulse.com/guides/best-desktop-app-frameworks-2026)

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
| macOS | Via pip (PyQt6-WebEngine); or Homebrew Qt6 |
| Windows | Via pip (PyQt6-WebEngine) |
| FreeBSD | `pkg install qt6-qtwebengine` |
| OpenBSD | `pkg_add qt6-qtwebengine` (amd64/aarch64 only) |

Electron has equivalent cross-platform reach, but each of the above requires a Node.js
runtime (30–80 MB) and a full Chromium binary (100–150 MB) bundled into the distributable.
Qt WebEngine on Linux/FreeBSD reuses the system-installed Chromium engine.
