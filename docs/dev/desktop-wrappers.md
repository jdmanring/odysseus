# Native Desktop Wrappers (Linux, macOS, Windows, *BSD)

Odysseus ships a native desktop application on each OS: a thin display wrapper
around a QtWebEngine window plus the normal Odysseus server. This document is
the reference for how the wrappers are built, installed, uninstalled, and
troubleshot, and for the design decisions that differ per platform.

## What the wrapper is

Each platform has a wrapper module that owns the window + process lifecycle:

| OS | Wrapper | Display Qt from |
|----|---------|-----------------|
| Linux | `qt_wrapper.py` | **system** PyQt6 |
| FreeBSD / OpenBSD | `qt_wrapper.py` | **system** PyQt6 |
| macOS | `mac_wrapper.py` | pip PyQt6 in the venv |
| Windows | `windows_wrapper.py` | pip PyQt6 in the venv |

The wrapper starts the Odysseus server (`uvicorn app:app`) as a child, opens a
QtWebEngine window on it, and manages memory reclaim, crash/hang recovery, the
single-instance guard, and platform niceties (Dock/taskbar identity, native
color picker, etc.).

## Architecture: one interpreter or two?

This is the key design split and it drives the PyQt6 sourcing.

- **Linux / FreeBSD / OpenBSD: two interpreters.** The display layer runs under
  the system `python3` so it can use the distro's system-built PyQt6/Qt, which
  has native Wayland integration and desktop theming. The Odysseus backend runs
  under the repo `venv` (where all server deps live). The venv deliberately does
  not contain PyQt6; the system `python3` could not import venv packages anyway.
- **macOS / Windows: one interpreter.** There is no system Qt to lean on, so
  PyQt6 is pip-installed into the venv and the wrapper runs under the venv
  `python`. Single interpreter, standard delivery.

### Why the PyQt6 sources differ (and why each is optimal)

- System PyQt6 on Linux/*BSD is optimal, not a compromise: native Wayland,
  distro Qt theming, and it avoids the ~250 MB Chromium binary the pip
  `PyQt6-WebEngine` wheel downloads. The cost (coupling to the distro's Qt
  version) is the right trade for a Wayland GUI. Installing it needs root
  (a system package), which is why the installer *guides* that one step.
- pip-into-venv PyQt6 on macOS/Windows is optimal there: no system Qt exists,
  one interpreter, no root needed.

### BSD platform hardening (qt_wrapper.py on FreeBSD/OpenBSD)

FreeBSD and OpenBSD reuse the Linux `qt_wrapper.py` as their display layer, so
its Linux-only assumptions must degrade *safely* off Linux. Three are
load-bearing — a miss on any produces a broken window, not a graceful fallback:

- **Force software rendering on non-Linux.** `_linux_software_render()` reads
  `/dev/dri` + `/sys/class/drm`; `/sys` is absent on BSD, so a bare `/dev/dri`
  node would wrongly report hardware and enable `--enable-gpu-rasterization`,
  which BSD's GPU-less Chromium can't honor (a **black window**). The function
  returns software-raster for any non-Linux platform.
- **Guard the QtDBus import.** The Freedesktop-portal colour picker imports
  `PyQt6.QtDBus`; a minimal BSD PyQt6 build without it must not crash the wrapper
  at import — the import is guarded (`_HAS_QTDBUS`) and falls back to the in-page
  eyedropper.
- **Disable the renderer memory purge when `/proc` RSS is unreadable.** The
  reclaim monitor reads RSS from `/proc`; on BSD that reads 0, which slips past
  the purge ceiling guard (`0` is falsy) and fires
  `Memory.forciblyPurgeJavaScriptMemory` every idle tick — and that CDP call
  **segfaults QtWebEngine's renderer** (exit 139) into a crash loop, i.e. a
  **white window**. `_PROC_RSS_OK` gates all forcible purges off on BSD; the
  reclaim sawtooth is a constrained-Linux optimization the platform runs
  correctly without. (PSI, `/proc/pressure`, is likewise disabled when absent.)
- **Guard the renderer-RSS *logging* read too, not only the purge.** The 60 s
  renderer-memory snapshot also reads `/proc/<pid>/status`; unguarded it errored
  every tick on BSD and spammed the log with `[MEM] error` lines (found on the
  FreeBSD bench, 2026-07-23). Both the snapshot and `_renderer_rss_kb()` now sit
  behind `_PROC_RSS_OK`, matching the host-RSS read.

The rule: any `/proc`-, `/sys`-, or DBus-dependent path in the shared wrapper
must **no-op, not error**, when the interface is absent.

### Native theming (About dialog, menus) follows the desktop where it can

Native Qt surfaces — the About dialog above all — follow the OS light/dark
scheme via `QStyleHints.colorScheme()` (the shared `qt_about.py`). Two caveats
on BSD, both verified on the FreeBSD bench:

- Qt only reports a scheme when a platform-theme plugin is active. Under a full
  KDE session (`XDG_CURRENT_DESKTOP=KDE`) Qt auto-loads `KDEPlasmaPlatformTheme`
  and `colorScheme()` returns Dark/Light correctly, so the About dialog matches
  the desktop. Launched from a **stripped environment** (e.g. an SSH shell that
  forwards only `DISPLAY`), `XDG_CURRENT_DESKTOP` is absent, no plugin loads,
  `colorScheme()` is `Unknown`, and the Qt palette defaults to light — so native
  chrome renders light regardless of the desktop's setting. A `.desktop`
  menu-launch always carries the full session env and themes correctly.
- When the scheme is `Unknown`, `qt_about` falls back to the window-palette
  lightness and, either way, paints a **soft** surface — never a harsh pure
  white (the original FreeBSD complaint).

## Installing

There is a single **from-scratch** entry point per OS (provision the Python
environment **and** install the native app) and a single **app-install** entry
point (install the native app around an existing venv).

| OS | From scratch (provision + install) | App install only |
|----|-----------------------------------|------------------|
| Linux / FreeBSD / OpenBSD | `./setup.sh` | `./install.sh` |
| macOS | `./start-macos.sh` (sets up + runs), then `./install.sh` | `./install.sh` (= `build-mac-app.sh`) |
| Windows | `powershell -File .\setup.ps1` | `install.bat` |

`install.sh` dispatches by `uname` to the per-OS builder
(`build-linux-app.sh` / `build-freebsd-app.sh` / `build-openbsd-app.sh` /
`build-mac-app.sh`). All builders **install in one run**: the XDG `.desktop`
entry on Linux/*BSD, the `/Applications` bundle + Dock pin on macOS, the
Start-Menu/Desktop shortcuts on Windows. On macOS, `--build-only` produces
`dist/` + the `.dmg` without installing.

`setup.sh` never runs a privileged command (per project policy): when a system
package (Python or PyQt6) is missing it prints the exact
`sudo pacman -S …` / `sudo apt install …` / `doas pkg_add …` command and stops,
so the one privileged step is yours.

### Semantic-memory prerequisites (fastembed / onnxruntime)

`requirements.txt` pulls in `chromadb-client` + `fastembed`, which power semantic
memory, RAG, and personal-doc retrieval. `fastembed` loads `onnxruntime`, whose
**native** runtime has platform prerequisites pip cannot provide — and a silent
failure demotes memory to keyword search unnoticed. The installers run
`tooling/verify_memory_stack.py` after `pip install`, which imports both and
prints a platform-specific fix on failure:

| Platform | Native prerequisite | Handled by |
|----------|---------------------|------------|
| Linux / macOS | prebuilt PyPI wheels — nothing extra | (works out of the box) |
| Windows | Microsoft Visual C++ Redistributable (onnxruntime's DLL links against it) | `setup.ps1` auto-installs it |
| FreeBSD | **not currently working** — `py-rust-stemmers` needs the Rust toolchain, and a numpy version pin forces a source build; memory runs **keyword-only** | documented in `build-freebsd-app.sh`; verifier flags it |

Run the check standalone any time: `venv/bin/python tooling/verify_memory_stack.py`
(exit 0 = healthy, 1 = degraded with remediation).

### What gets installed, per OS

- **Linux / FreeBSD / OpenBSD**
  - `~/.local/bin/odysseus` — launcher script
  - `~/.local/share/applications/odysseus.desktop` — menu entry
  - `~/.local/share/icons/hicolor/scalable/apps/odysseus.svg` — icon
- **macOS**
  - `/Applications/Odysseus.app` — bundle (ad-hoc codesigned)
  - a Dock pin (fresh, URL-only, so a reinstall's new inode is picked up)
  - `dist/Odysseus.dmg` — drag-to-Applications image
- **Windows**
  - Start-Menu and Desktop `.lnk` shortcuts with the AppUserModelID stamped
    (so taskbar pinning and window identity match)

## Uninstalling

- **Linux / FreeBSD / OpenBSD**
  ```sh
  rm -f ~/.local/bin/odysseus \
        ~/.local/share/applications/odysseus.desktop \
        ~/.local/share/icons/hicolor/scalable/apps/odysseus.svg
  update-desktop-database ~/.local/share/applications 2>/dev/null || true
  ```
- **macOS**
  ```sh
  rm -rf /Applications/Odysseus.app
  # then remove the Dock pin: right-click the icon -> Options -> Remove from Dock
  # (or re-run the pin helper against a non-existent path and `killall Dock`).
  ```
- **Windows**: delete the Start-Menu and Desktop `Odysseus` shortcuts.

The repo checkout, `venv/`, and your `data/` are never touched by uninstall.
Remove the checkout directory to remove those.

## Cookbook background tasks (downloads and serves)

Cookbook runs model downloads and serves as **background** jobs so they survive
a browser/SSE disconnect. Two launch models:

- **tmux:** on Linux (and any host with tmux), and on all remote hosts.
- **detached process + logfile:** on macOS and Windows (tmux is not in
  their base systems) and on any local POSIX host without tmux. The job runs
  detached, writing `<session>.log` and `<session>.pid` under the session dir
  (`tempfile.gettempdir()/odysseus-tmux`); the status poller reads those files.

The poller distinguishes the two per task by the pidfile's presence, so launch
and polling always agree for the task's whole life.

**Download backend.** aria2c (fast, multi-connection) is **the** downloader:
the fork's replacement for the flaky `hf_transfer`, not an optional accelerator.
It is auto-installed by `BinManager` (static build) on Linux and Windows; on
macOS, which has no static build, it is installed during setup
(`start-macos.sh` → `brew install aria2`, or conda-forge), and the bundle
launcher prepends the usual tool dirs (`/opt/homebrew/bin`, `~/bin`, …) so it is
found. The built-in Python (`huggingface_hub`) downloader is an **emergency
fallback only**, used when aria2c genuinely can't be provisioned, never as the
intended path.

**Stopping.** Detached jobs are stopped by killing their **process group**
(`kill -pgid` / `os.killpg` locally; `taskkill /T` on Windows) so the downloader
child dies too, not just the shell.

## macOS window lifecycle (red button, fullscreen, zoom, reopen)

The macOS wrapper follows the native convention: the **red button hides the
window to the Dock** (the app keeps running and re-shows on Dock-click / Cmd-Tab),
while **⌘Q / Dock-Quit** fully quit. This matches how Apple's own single-window
apps behave (TextEdit, Notes) and is deliberate for a serving app: a careless
close must not tear down in-flight work.

The complication is the crash above. A `QWebEngineView` cannot be hidden while
the window is in native fullscreen or zoomed (maximized) without a reparent
null-deref, so the wrapper never hides from those states directly. It leaves
them first, then hides:

- **Fullscreen exit is event-driven.** Qt's `WindowStateChange` fires while macOS
  is still animating the exit, so hiding there is overridden by the finishing
  animation (the window reappears at normal size). The correct signal is the
  Cocoa `NSWindowDidExitFullScreenNotification`, observed via the Obj-C runtime
  (ctypes, the same mechanism used for `proc_pid_rusage`/`memorystatus`). The hide
  fires once, at true completion, and sticks on the first try (logged
  `retries=0`). It registers with `object:nil` so it survives Qt swapping the
  native `NSWindow`. Install is fully guarded; on any failure the code degrades to
  the retry path below, and a 1.5 s backstop timer guarantees the window can never
  be stranded visible.
- **Zoom exit uses a bounded retry.** A zoom (maximized, not fullscreen) exit has
  no completion notification, so that path hides on `WindowStateChange` and
  re-checks after 300 ms, re-hiding if the animation overrode it (capped; normally
  one retry). This is the fallback, used only where macOS gives no signal.
- **The window is invisible during the exit** (`setWindowOpacity(0)`), restored on
  the next show, so the user never sees it flash at normal size before it hides.
  The residual fullscreen-Space transition is macOS's own and is intentionally
  left alone. Apple's apps show the same, and it is not a per-app window
  animation to suppress.

**State is remembered like a native app.** Size and the zoomed/normal state are
saved (`saveGeometry` + `windowMaximized`) and restored on relaunch and on
Dock-reopen: a window that was zoomed before going fullscreen returns zoomed
rather than a plain window, matching macOS's pre-fullscreen-frame restoration.
The first-run default is a plain 1000×650 window (nothing scaled to the screen);
after that the remembered size wins.

## System tray and close-to-tray lifecycle

Odysseus is a control plane for model servers and an API host, not just a viewer
(`app.py` binds `APP_BIND`, defaults to loopback; auth + reverse-proxy/tunnel
support exist for remote access). So the wrappers keep the local server reachable
after the window is closed, the way Ollama and LM Studio do.

- **Windows / Linux** get a `QSystemTrayIcon` (notification area / status tray).
  The close (X) button **hides to the tray** and leaves the embedded server —
  and any detached model server or download it manages — running, so the local
  API stays up. With the **Close to tray** toggle off, X quits instead of hiding.
- **macOS** already hides to the **Dock** on the red button (`setQuitOnLast
  WindowClosed(False)` + `closeEvent` hides; see the lifecycle section above), so
  the menu-bar item is additive. It is rendered by a **separate helper process**
  (`mac_tray_helper.py`, built on `rumps`): an `NSStatusItem` created inside the
  Qt process does not render on macOS 26 (Tahoe) — Qt's event dispatcher services
  it instead of an AppKit run loop — so a standalone helper with its own run loop
  is used. The helper talks to the wrapper over an `AF_UNIX` socket (a
  `QSocketNotifier` accepts on the Qt loop, no polling): one-word verbs for
  actions, and a periodic `status` query the wrapper answers with
  `running|host:port|expose` to keep the helper's status line and Expose
  checkmark live. There is no Close-to-tray toggle on macOS — hiding on the red
  button is the native convention.

### Tray menu (all three OSes)

Modelled on the server-runner convention shared by Docker Desktop, Tailscale,
Syncthing, and Ollama — a background server you keep resident should be
controllable from the tray, not merely opened and quit:

| Item | Behaviour |
|------|-----------|
| Status line (disabled) | a coloured dot + `Running — host:port` / `Stopped` / `Restarting…`, refreshed each time the menu opens (`QMenu.aboutToShow`; a 3 s poll on macOS). Green running / red stopped / amber transitional. The Qt wrappers paint the dot via the shared `qt_status_dot.py` (colour pinned for the disabled action's Disabled icon mode so it isn't greyed); macOS draws a native `NSImage` dot with an emoji fallback. |
| Open Odysseus | show / raise the window |
| Open in Browser | open `http://host:port` in the default browser |
| Copy Server URL | copy that URL to the clipboard |
| Settings… | open the settings modal (drives the same DOM the app does: clicks `#rail-settings` → falls back to `#user-bar-settings` / `#tool-settings-btn`) |
| Shortcut Keys… | open settings on the Keyboard Shortcuts tab (`[data-settings-tab="shortcuts"]`) |
| Expose to Network | persisted `QSettings` toggle (`exposeToNetwork`); rebinds the server to `0.0.0.0`; **enabling is gated behind a confirmation** — it changes security posture |
| View Logs | open the `logs/` directory |
| Restart Server | stop + start the uvicorn process off the GUI thread (`_ServerRestartThread`), then reload the webview |
| Close to tray | checkable, `QSettings` `closeToTray` (default on); Windows/Linux only |
| README / About Odysseus | open the README; show the native About dialog — theme-aware (light/dark) via the shared `qt_about.py`: icon, version from `src/constants.py`, copyright, AGPL notice, links |
| Quit Odysseus | real teardown |

- **`settingsModule` is not a window global.** It is an ES-module export, so the
  Settings / Shortcut Keys items must drive the DOM the app itself uses rather
  than call `window.settingsModule.open()` (which resolves to `undefined`).
- **Expose-aware host.** `start_server()` reads `exposeToNetwork` and tracks the
  live bind host; `_reachable_host()` resolves the primary LAN IP when bound to
  `0.0.0.0` (that address is not itself connectable) so the URL/status items are
  useful. `restart_server()` terminates only uvicorn and relaunches — unlike
  `stop_server()` it leaves the CDP executor intact.
- **Availability guard.** The `QSystemTrayIcon` is created only when
  `QSystemTrayIcon.isSystemTrayAvailable()` is true. On a session with no tray
  host (a minimal WM with no StatusNotifier), the wrapper falls back to
  quit-on-close so the window can never be hidden with no way to bring it back.
- **Teardown is single-pathed.** A real quit (tray Quit, toggle off, or no tray)
  routes through `app.aboutToQuit` → release the web page, then `stop_server()`;
  on macOS it also terminates the helper process and removes the socket. Detached
  model servers/downloads are independent and intentionally survive.
- **The Expose toggle is a convenience, not the production serve path.** It binds
  `0.0.0.0` for the current GUI session so another device on a trusted LAN can
  reach the API. To run Odysseus as a real always-on service ("run it on a
  server, remote in through the API"), still run the server headless under a
  service manager — a Windows Service, systemd/s6, or launchd — not the GUI
  wrapper, which needs an interactive desktop session.

## Troubleshooting

- **Linux/*BSD: "System PyQt6 with WebEngine not found."** Install the system
  package and re-run `./setup.sh`:
  - Arch: `sudo pacman -S python-pyqt6 python-pyqt6-webengine`
  - Debian/Ubuntu: `sudo apt install python3-pyqt6 python3-pyqt6.qtwebengine`
  - Fedora: `sudo dnf install python3-pyqt6 python3-pyqt6-webengine`
  - FreeBSD: `doas pkg install py311-qt6-webengine py311-qt6-webchannel py311-dbus-python`
  - OpenBSD: `doas pkg_add py3-qt6webengine` (pulls `py3-qt6` + `qt6-qtwebengine`;
    the bindings package is **`py3-qt6webengine`**, not `py3-pyqt6-webengine`).
    The venv must be created `--system-site-packages` to see the system PyQt6.
    Server deps: `pkg_add py3-python-multipart` (**not** `py3-multipart`, a
    different project FastAPI won't accept) and `py3-dateutil`; a few pure-python
    deps (`aiofiles`, `pydantic-settings`) are unpackaged and need pip.
- **macOS: "incompatible architecture" on Apple Silicon.** The venv was built
  with an x86/universal Python; the `.app` needs an **arm64** interpreter. Use
  `./start-macos.sh` (it requires Homebrew's arm64 Python) or rebuild the venv
  with `/opt/homebrew/bin/python3`.
- **Downloads are slow / not using aria2c.** aria2c isn't on the app's PATH.
  Install it (`brew install aria2`, or conda-forge, or your PM) and re-launch;
  on macOS the bundle launcher already searches the common locations.
- **Blank window / flicker on a VM or GPU-less box.** Chromium falls back to
  software rendering (SwiftShader/llvmpipe); the wrapper detects this and does
  not force GPU rasterization. Reduced smoothness here is the software renderer,
  not a bug.
- **A macOS VM cannot use the host GPU, so the bench is always software-rendered.**
  A macOS guest has no virtio-gpu driver, so it cannot consume the paravirtual 3D
  acceleration (VirGL) the host offers, even when the VM is configured with
  `virtio-vga accel3d='yes'`. It also has no driver for a host integrated GPU
  (e.g. an AMD Ryzen iGPU was never shipped in a Mac). macOS VM acceleration is
  only possible by passing through a discrete GPU that macOS natively supports
  (certain AMD Polaris/Vega/Navi cards). Consequence: flicker, garble, and
  transition jank seen on the macOS bench are software-renderer artifacts and do
  not reproduce on a real Mac with Metal. Treat the bench as functional-test
  only; judge rendering on real hardware.
- **macOS "Odysseus quit unexpectedly" + WindowServer freeze/garble.** Root
  cause (corrected after an earlier misdiagnosis): it happened when a window in
  **native fullscreen** (green button, a separate macOS Space) *or zoomed*
  (maximized) was closed. Hiding the `QWebEngineView` while in that state
  reparents it (`QWidgetPrivate::reparentFocusWidgets` during the Space/zoom
  transition), and `setVisible()` fired on the view mid-reparent null-derefs on
  the CrBrowserMain thread. The crash then leaves WindowServer with a corrupt
  full-screen composite (frozen/garbled screen; the Dock won't unhide). It is a
  documented QtWebEngine reparent-on-teardown class (Zeal #577, Inkscape,
  ChimeraX #3761). A normal windowed close never triggered it. See the **window
  lifecycle** section below for the fix, which is the current design (an earlier
  `os._exit`-on-quit change addressed a *different*, mis-scoped teardown path and
  did NOT fix this; it remains only as quit-path hygiene).
- **macOS bench: display and input freeze while SSH stays alive (a hang, not a
  crash).** Distinct from the crash above: the app stays healthy (steady `[MEM]`
  telemetry, CDP `responsive:true` on `:9222`) but the guest's mouse, keyboard,
  and screen freeze. This is the **software WindowServer wedging** on the
  GPU-less VM under sustained load — not the app. A hang writes **no** crash
  report (only a `shutdownStall` if you then reboot), so a clean crash count
  proves nothing about it. It does not reproduce on real Mac hardware with Metal.
  Recover from the host over SSH without a full reboot via
  `sudo killall WindowServer` (drops to loginwindow, restores input in seconds),
  or `sudo reboot` for a clean restart. The reparent-crash class above is a
  separate, fixed issue — confirm which you have by checking for a *new*
  `python3.12-*.ips` (crash) vs none (hang).
- **macOS crash reports** live in `~/Library/Logs/DiagnosticReports/*.ips`
  (per-user) and `/Library/Logs/DiagnosticReports/` (system). Each is JSON after
  the first line; read the faulting thread's frames to find the cause. For an
  intermittent crash, count reports before/after a triggered action to attribute
  it, and confirm the *current* build still produces a *new* one.
- **Stale JS/CSS after a redeploy (e.g. an old download card, stuck spinner).**
  The app is a PWA with a service worker (`static/sw.js`). A persisted worker and
  its Cache Storage survive app restarts, so a redeployed unversioned module
  (ES-module imports carry no `?v=` buster) could be served stale indefinitely —
  closing and reopening the app did not help. Fixed: `static/index.html`
  registers the worker with a forced `reg.update()` on every load and reloads
  once when a new worker activates over an existing controller, so a bumped
  `CACHE_NAME` propagates on the next load. QtWebEngine's HTTP cache is also
  in-memory (`MemoryHttpCache`) so it never persists a stale disk copy. To force
  a refresh manually over the debug port: unregister the worker + delete caches
  via CDP `Runtime.evaluate`, then `Page.reload {ignoreCache:true}`.
- **Windows bench: SSH default shell is PowerShell.** The OpenSSH server on the
  Windows bench is configured (`HKLM\SOFTWARE\OpenSSH`: `DefaultShell` =
  `…\WindowsPowerShell\v1.0\powershell.exe`, `DefaultShellCommandOption` =
  `-Command`) so `ssh win11 '<cmd>'` runs PowerShell, matching the platform's
  intended shell. Pass real Python via a `.ps1`/`.py` script file rather than
  inline `python -c` — quoting code through any remote shell is fragile
  regardless of which shell it is.

## Tests

- Behavioral: `test_linux_installer_e2e.py` (runs the real installer in a
  sandbox `$HOME`), `test_process_group_kill.py` (real leader+child tree),
  `test_download_status_classification.py`, `test_macos_dock_pin.py`.
- Contract/wiring guards: `test_setup_provisioner.py`,
  `test_macos_download_detached.py`, `test_macos_serve_detached.py`,
  `test_detached_stop_kill.py`, `test_macos_wrapper_lifecycle.py`,
  `test_macos_build_icns_codesign.py`.

macOS lifecycle, downloads (both backends), serve launch, stop/kill, and the
Dock icon were additionally verified end-to-end on a macOS bench, and the Linux
installer + setup path on an Arch machine.

**FreeBSD — bench-verified end-to-end (2026-07-23), FreeBSD 15.1 / KDE Plasma 6 /
Qt 6.11.1** (proof screenshot kept locally under the gitignored
`docs/fork/screenshots/`): `build-freebsd-app.sh` installs cleanly; the main window renders with **no
white-screen / renderer crash-loop** (the `_PROC_RSS_OK` guard holds — zero
`RENDERER Crashed` over a sustained idle run); tray icon + full tray menu +
Quit work; single-instance rejects a second launch (`[SINGLETON] already
running`); close-to-tray works; and the About dialog renders theme-matched.
Verified both by machine checks (logs, port, singleton) and by eye.

**OpenBSD — bench-verified (2026-07-23), OpenBSD 7.9 / KDE Plasma 6 / Qt 6.10.2:**
after provisioning (`py3-qt6webengine`, `--system-site-packages` venv, the server
deps above), `build-openbsd-app.sh` installs cleanly, the backend serves, the main
window renders the app UI (dark, software render, **no white-screen/crash-loop** —
0 `RENDERER Crashed`, no `[MEM] error`), single-instance rejects a second launch
(`[SINGLETON] already running`), and the About dialog renders theme-matched
(`colorScheme` Dark via `KDEPlasmaPlatformTheme6`). Render/About/single-instance were
checked by launching onto a bare `:0`; **tray icon + full tray menu + close-to-tray +
Quit were then verified by eye in a full Plasma session** (a bare X server has no
StatusNotifier host, so there the wrapper correctly takes its `system tray
unavailable; X will quit` fallback).

Windows `setup.*` is written but not yet bench-verified.
