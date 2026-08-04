# PR Draft: fix/settings-shortcut-resurrection -> odysseus-dev/odysseus:dev

**Branch:** `fix/settings-shortcut-resurrection`
**Status:** Ready to file
**Base:** cut from `upstream-mirror`, 2 files, +35/-10

---

## Title

`fix(shortcuts): the settings keybind opens Settings, never a remembered window`

---

## Summary

### Problem

`_toggleActiveWindow` remembered the last tool window it closed (`_lastWindow`)
and reopened **that** when the shortcut fired with nothing open.

So: close Brain with the shortcut once, and every later press of the *Settings*
shortcut resurrects Brain, on its last tab, indefinitely — until some other
window happens to overwrite the memory.

From the user's side this reads as windows opening themselves. The binding is
named for Settings and does something else, and the trigger is invisible because
the cause was a Brain close that may have been minutes earlier.

### Fix

Keep the useful half: the shortcut still closes whatever tool window is open.
When nothing is open, open **Settings** — the binding's own name.

Dropping `_lastWindow` also removes a piece of cross-invocation state that had no
other reader, so the shortcut becomes a pure function of what is currently open.

---

## Verification

**2 passed**, measured 2026-08-03: the shortcut opens Settings when nothing is
open, and closing a different tool window does not change what it later opens.

---

## Scope

`static/js/keyboard-shortcuts.js` (+18/-10) and one test file.
