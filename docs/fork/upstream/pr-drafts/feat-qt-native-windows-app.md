# PR Draft: feat/qt-native-windows-app -> odysseus-dev/odysseus:dev

**Branch:** `feat/qt-native-windows-app`
**Status:** Ready to file - **stacks on `feat/qt-native-linux-app`**, file that first
**Base:** cut from `upstream-mirror`, 9 files, +2044/-11

---

## Title

`feat(windows): native Windows desktop application`

---

## Summary

Odysseus as a native Windows app, hardened to parity with the Linux
`qt_wrapper.py`, which is the reference implementation.

### Windows-specific behaviour worth reviewing

**Dark title bar.** The caption bar is painted by DWM, not Qt, and defaults to
light. Qt 6 does not opt windows into dark mode, and Odysseus themes
independently of the Windows light/dark setting - so a dark in-app theme sat
under a bright frame.

Fixed with `DwmSetWindowAttribute(DWMWA_USE_IMMERSIVE_DARK_MODE)` via ctypes
after the window is shown, keyed off **the Odysseus theme's own luminance** so
the frame tracks the theme the user actually sees rather than the OS setting.
Attribute 20 (Win10 20H1+/Win11) with a fallback to 19 (older Win10).

**The native call is fully guarded** - any failure leaves the default light
frame. A cosmetic improvement must not be able to break window creation, so the
worst case is the current appearance rather than an error.

Verified on Windows 11 24H2 (build 26100): `DwmSetWindowAttribute` returns
`S_OK` for attribute 20.

---

## Verification

**14 passed**, measured 2026-08-03.

`windows_wrapper.py` cannot be imported on Linux, so the contract is pinned
statically, matching the other wrapper suites. The DWM call was confirmed live on
the Windows 11 bench as above.

---

## Scope

`windows_wrapper.py` (+1640), build tooling, and 4 test files.
