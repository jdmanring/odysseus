# PR Draft: feat/qt-native-macos-app -> odysseus-dev/odysseus:dev

**Branch:** `feat/qt-native-macos-app`
**Status:** Ready to file - **stacks on `feat/qt-native-linux-app`**, file that first
**Base:** cut from `upstream-mirror`, 14 files, +2813/-11

---

## Title

`feat(macos): native macOS desktop application`

---

## Summary

Odysseus as a native macOS app, derived from the Linux `qt_wrapper.py` rather
than reimplemented beside it.

### What "native" has to mean on macOS

The platform conventions are not optional, and getting them wrong makes the app
feel broken in ways a Linux port would not surface:

- **The red button hides, it does not quit.** `setQuitOnLastWindowClosed(False)`
  plus a `closeEvent` that vetoes the close and hides to the Dock. A real quit
  (⌘Q, Dock Quit, quit Apple Event) arrives as `QEvent.Quit` and is flagged by a
  filter **before** `closeEvent` runs, so a genuine quit is not vetoed.
- **⌘Q must not depend on the platform posting the event.** Bound explicitly and
  deterministically.
- **Exit-fullscreen animation can override a hide.** Pressing red in fullscreen
  exits fullscreen first (green-button behaviour), and macOS's animation can undo
  a hide issued before it completes - the window reappears at normal size. So
  `_hide_to_dock()` verifies shortly after and re-hides until it sticks, capped.
- **Reopen must not fight the hide.** A deliberate red-button hide bounces the app
  Inactive -> Active, which would instantly un-hide it. `_last_hide_ts` lets the
  activation handler tell that from a real Dock-click reopen made later.
- Native Edit menu, `.icns` generation, code signing, Dock pinning.

Each of those is a small amount of code and a specific macOS behaviour that has
to be discovered; they are the reason this is a port rather than a rebuild.

---

## Verification

**28 passed, 2 skipped**, measured 2026-08-03.

`mac_wrapper.py` **cannot be imported off macOS** - PyQt plus `os.dup2` plus
ctypes libSystem side effects at import time - so the contract is pinned
statically, matching the other wrapper suites in this repo.

The behaviours themselves were **verified live on a Tahoe bench** by driving
`QEvent.Quit` / `closeAllWindows` headlessly (TCC blocks UI scripting): red
button hides and the app survives, reopen re-shows, quit tears down.

One assertion was corrected today: `closeEvent` now delegates to
`_hide_to_dock()` rather than calling `self.hide()` directly, so the test
followed the call - **and a second test was added that the helper still hides and
still records `_last_hide_ts`**, because a delegation assertion alone would pass
against a helper that had stopped hiding.

---

## Scope

`mac_wrapper.py`, `build-macos-app.sh`, `tooling/macos_dock_pin.py`, and 6 test
files.
