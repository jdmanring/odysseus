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
  API stays up. The tray menu has **Open Odysseus**, a checkable **Close to tray**
  toggle (persisted in `QSettings` under `closeToTray`, default on), and **Quit
  Odysseus**. With the toggle off, X quits instead of hiding.
- **macOS** already hides to the **Dock** on the red button (`setQuitOnLast
  WindowClosed(False)` + `closeEvent` hides; see the lifecycle section above), so
  the tray is purely additive: a menu-bar status item (`NSStatusItem`) with Open
  and Quit. No close-to-tray toggle — hiding on close is the native convention.
- **Availability guard.** The tray is created only when
  `QSystemTrayIcon.isSystemTrayAvailable()` is true. On a session with no tray
  host (a minimal WM with no StatusNotifier), the wrapper falls back to
  quit-on-close so the window can never be hidden with no way to bring it back.
- **Teardown is single-pathed.** A real quit (tray Quit, toggle off, or no tray)
  routes through `app.aboutToQuit` → release the web page, then `stop_server()`.
  Detached model servers/downloads are independent and intentionally survive.
- **Not the remote-serve mechanism.** A tray needs an interactive desktop
  session. To expose Odysseus to other machines ("run it on a server, remote in
  through the API"), run the server headless (`APP_BIND=0.0.0.0`) under a service
  manager — a Windows Service, systemd/s6, or launchd — not the GUI wrapper.

## Troubleshooting

- **Linux/*BSD: "System PyQt6 with WebEngine not found."** Install the system
  package and re-run `./setup.sh`:
  - Arch: `sudo pacman -S python-pyqt6 python-pyqt6-webengine`
  - Debian/Ubuntu: `sudo apt install python3-pyqt6 python3-pyqt6.qtwebengine`
  - Fedora: `sudo dnf install python3-pyqt6 python3-pyqt6-webengine`
  - FreeBSD: `doas pkg install py311-qt6-webengine py311-qt6-webchannel py311-dbus-python`
  - OpenBSD: `doas pkg_add qt6-qtwebengine py3-pyqt6-webengine`
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
installer + setup path on an Arch machine. FreeBSD/OpenBSD/Windows `setup.*` are
written but not yet bench-verified.
