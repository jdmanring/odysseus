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

- **Linux / FreeBSD / OpenBSD — two interpreters.** The display layer runs under
  the **system** `python3` so it can use the distro's system-built PyQt6/Qt,
  which has native **Wayland** integration and desktop theming. The Odysseus
  **backend** runs under the repo `venv` (where all server deps live). So the
  venv deliberately does **not** contain PyQt6 — the system `python3` could not
  import venv packages anyway.
- **macOS / Windows — one interpreter.** There is no system Qt to lean on, so
  PyQt6 is pip-installed into the venv and the wrapper runs under the venv
  `python`. Single interpreter, standard delivery.

### Why the PyQt6 sources differ (and why each is optimal)

- System PyQt6 on Linux/*BSD is optimal, not a compromise: native Wayland,
  distro Qt theming, and it avoids the ~250 MB Chromium binary the pip
  `PyQt6-WebEngine` wheel downloads. The cost — coupling to the distro's Qt
  version — is the right trade for a Wayland GUI. Installing it needs root
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
`build-mac-app.sh`). All builders **install in one run** — the XDG `.desktop`
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

The repo checkout, `venv/`, and your `data/` are never touched by uninstall —
remove the checkout directory to remove those.

## Cookbook background tasks (downloads and serves)

Cookbook runs model downloads and serves as **background** jobs so they survive
a browser/SSE disconnect. Two launch models:

- **tmux** — on Linux (and any host with tmux), and on all **remote** hosts.
- **detached process + logfile** — on **macOS and Windows** (tmux is not in
  their base systems) and on any local POSIX host without tmux. The job runs
  detached, writing `<session>.log` and `<session>.pid` under the session dir
  (`tempfile.gettempdir()/odysseus-tmux`); the status poller reads those files.

The poller distinguishes the two per task by the pidfile's presence, so launch
and polling always agree for the task's whole life.

**Download backends.** aria2c (fast, multi-connection) is used when a system
`aria2c` is on the app's `PATH`; otherwise Cookbook falls back automatically to
the built-in Python (`huggingface_hub`) downloader. On macOS the bundle launcher
prepends the usual tool dirs (`/opt/homebrew/bin`, `~/bin`, …) so a
Homebrew/MacPorts/conda/user `aria2c` is found.

**Stopping.** Detached jobs are stopped by killing their **process group**
(`kill -pgid` / `os.killpg` locally; `taskkill /T` on Windows) so the downloader
child dies too, not just the shell.

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
  not force GPU rasterization. Expect reduced smoothness — it's the software
  renderer, not a bug.
- **macOS "Odysseus quit unexpectedly" on quit.** Fixed: QtWebEngine 6.11
  intermittently null-derefs in `QWebEnginePage::setVisible` while Qt destroys
  the web view at shutdown. The wrapper now hard-exits (`os._exit`) after saving
  state and stopping the server, pre-empting Qt's racy WebEngine teardown — the
  app was already fully cleaned up, so nothing is lost. If you still see it on an
  older build, update to the current `mac_wrapper.py`.
- **macOS crash reports** live in `~/Library/Logs/DiagnosticReports/*.ips`
  (per-user) and `/Library/Logs/DiagnosticReports/` (system). Each is JSON after
  the first line; read the faulting thread's frames to find the cause. For an
  intermittent crash, count reports before/after a triggered action to attribute
  it, and confirm the *current* build still produces a *new* one.

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
