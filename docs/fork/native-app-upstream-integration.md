# Native desktop app ↔ upstream "native installers" — integration map

**Status:** analysis, 2026-07-21. Written after upstream (renamed to
`odysseus-dev/odysseus`, see below) began advertising "native installers" in its
README, raising the question of whether our native desktop app was superseded.
**It was not.** This doc records how the two relate, where they collide, and what
to reconcile before a native-app upstream PR.

## Upstream repository rename

The upstream repo was renamed/transferred from `pewdiepie-archdaemon/odysseus` to
**`odysseus-dev/odysseus`**. Both URLs resolve to the same HEAD and `gh api`
reports `full_name: odysseus-dev/odysseus` for each, so the old name is a GitHub
redirect. The fork's `upstream` remote fetch URL is updated to the new name (push
stays disabled). Upstream-owned files still carrying the old name (README,
CONTRIBUTING, `.github/` templates) are left alone — they take the new name when
we sync from upstream, not by hand.

## What upstream's "native installers" actually are

Server-launch scripts and a browser launcher — **not** a GUI application:

- `start-macos.sh`, `launch-windows.ps1`: set up a venv and run `uvicorn`; the
  UI is a browser pointed at `127.0.0.1:7000`/`7860`.
- `build-macos-app.sh`: builds `dist/Odysseus.app` — a **bash launcher** that
  starts uvicorn and opens the UI in a Chromium `--app` window (Chrome/Edge/
  Brave/Chromium), falling back to the default browser, plus a drag-to-
  Applications `.dmg`. No PyQt6, no native window, no tray/Dock, no lifecycle.

No PyQt6/QtWebEngine, system tray, hide-to-Dock, or `desktop-wrappers` doc exists
upstream.

## What the fork adds (no upstream equivalent)

A real native desktop application:

- `mac_wrapper.py` / `qt_wrapper.py` / `windows_wrapper.py` — PyQt6/QtWebEngine
  windows with window-lifecycle management, system tray / menu-bar item,
  hide-to-Dock (macOS), GPU-flag handling, a renderer memory monitor, and crash
  recovery.
- One-command installers `setup.sh` / `setup.ps1` / `install.sh` / `install.bat`
  and Qt app builders `build-mac-app.sh` / `build-linux-app.sh` /
  `build-windows-app.ps1`.
- `docs/dev/desktop-wrappers.md`.

## Integration map (fork vs `upstream/dev`)

| File | Ours | Upstream | Relationship |
|------|------|----------|--------------|
| `mac_wrapper.py`, `qt_wrapper.py`, `windows_wrapper.py` | ✓ | — | fork-only, additive |
| `setup.sh`, `setup.ps1`, `install.sh`, `install.bat` | ✓ | — | fork-only, additive |
| `build-mac-app.sh`, `build-linux-app.sh`, `build-windows-app.ps1` | ✓ | — | fork-only, additive |
| `launch-windows.ps1` | ✓ | ✓ | **identical** (inherited, untouched) |
| `build-windows-portable.ps1` | ✓ | ✓ | **identical** (inherited, untouched) |
| `start-macos.sh` | ✓ | ✓ | **differs** (fork drops the aria2c brew line) |
| `build-macos-app.sh` | ✓ | ✓ | **differs** (the Chrome-launcher; see below) |

So the native app is mostly **additive** — new files that slot alongside
upstream's installers without collision. Two shared files differ and are the only
friction points.

## How they coexist (already, by design)

The fork deliberately keeps **both** macOS paths, differentiated by filename:

- `build-mac-app.sh` → the **Qt native** app (`dist/Odysseus.app` = the PyQt6
  wrapper) + `.dmg`. This is the primary, full-featured path.
- `build-macos-app.sh` → the **Chrome `--app` launcher** (upstream's approach,
  no Qt dependency, browser-based UI) + `.dmg`.

`build-mac-app.sh`'s own header points at `build-macos-app.sh` as the "no Qt
dependency" alternative. The Qt native app is thus layered on top of the browser
launcher, not a replacement for it — a user who does not want PyQt6 can still use
the lightweight launcher.

## The "competing" macOS wrapper — verdict

Upstream's `build-macos-app.sh` is a browser-in-app-mode launcher. Compared with
`mac_wrapper.py` it is primitive (no native window, tray, or Dock behavior), but
it is not worthless and does two things cleanly worth keeping:

- Produces a distributable **`.dmg`** (drag-to-Applications) — our
  `build-mac-app.sh` already does this too.
- Graceful **already-running** detection (curl the port, just open the UI),
  Chromium-`--app` detection across Chrome/Edge/Brave/Chromium with a
  default-browser fallback, and `.icns` icon generation via `sips`.

**Verdict: keep it, don't replace it.** It is the legitimate no-Qt fallback. The
Qt native app is the primary experience; the launcher stays for users who won't
install PyQt6. No functionality of ours depends on removing it.

## Reconcile before a native-app upstream PR

1. **`build-macos-app.sh` and `start-macos.sh` differ** from upstream and will
   conflict on a PR branch. Rebase onto the current `upstream/dev` and re-apply
   only the fork's intentional deltas (the Qt path is separate files; keep the
   shared files as close to upstream as possible).
2. **Two similarly-named macOS builders** (`build-mac-app.sh` vs
   `build-macos-app.sh`) will confuse an upstream reviewer. Before filing,
   decide the framing: present the Qt app builder as the addition and keep
   upstream's launcher untouched, with a one-line note in the setup guide
   distinguishing them ("Qt native app" vs "browser launcher").
3. The wrappers + installers + `desktop-wrappers.md` are pure additions and PR
   cleanly on their own.
