# PR Draft: fix/editor-redo-shortcut → pewdiepie-archdaemon/odysseus:dev

**Branch:** `fix/editor-redo-shortcut`
**Fork issue:** [#100](https://github.com/jdmanring/odysseus/issues/100)
**Status:** Single clean commit. File the upstream issue first, fill `Fixes #___`, then open the PR.

## Upstream PR title
`fix(editor): Ctrl+Shift+Z (redo) never fires — key check misses uppercase 'Z'`

## Summary

### Problem
The gallery editor's redo shortcut is gated on `e.key === 'z'` in
`static/js/editor/keyboard-shortcuts.js`. With Shift held, `e.key` for the Z key is
the uppercase `'Z'`, so the check never matches and `redo()` is unreachable —
**Ctrl+Shift+Z does nothing** (plain Ctrl+Z / undo works). The same file already
matches both cases for its other Shift chords (`'D'`/`'d'`, `'s'`/`'S'`).

### Fix
Accept both `'z'` and `'Z'` in the redo branch. One-line condition change.

## How to Test
1. Open the gallery editor and make an edit.
2. Press Ctrl+Z → the edit is undone.
3. Press **Ctrl+Shift+Z**.
   - **Expected:** the edit is redone.
   - **Before this fix:** nothing happens.

### Tests
`tests/test_editor_redo_shortcut.py` — asserts the handler accepts both `'z'` and
`'Z'` for the redo branch (would fail against the lowercase-only pre-fix version).

## Scope
One file (`static/js/editor/keyboard-shortcuts.js`), condition only. No behavior
change to any other shortcut.

## Target branch
`dev` (never `main`).

## Fixes
`Fixes #___` (fill with the upstream issue number after filing).
