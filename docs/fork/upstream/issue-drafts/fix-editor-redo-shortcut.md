# Upstream Issue Draft: fix-editor-redo-shortcut

**File on:** `pewdiepie-archdaemon/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/fix-editor-redo-shortcut.md`
**Branch:** `fix/editor-redo-shortcut`
**Type:** Bug

## Title
`fix(editor): Ctrl+Shift+Z (redo) never fires — key check misses uppercase 'Z'`

## Body
In the gallery editor's keyboard handler (`static/js/editor/keyboard-shortcuts.js`),
the redo shortcut is gated on `e.key === 'z'`. When Shift is held, `e.key` for the
Z key is the **uppercase** `'Z'`, so the lowercase-only comparison never matches and
the `redo()` branch is unreachable — **Ctrl+Shift+Z does nothing** (plain Ctrl+Z /
undo works). The file already handles both cases for its other Shift chords
(`'D'`/`'d'`, `'s'`/`'S'`), so this is an inconsistency.

**Steps to reproduce:** Open the gallery editor, make an edit, Ctrl+Z (undoes),
Ctrl+Shift+Z (expected: redo) → nothing happens.

**Fix:** accept both `'z'` and `'Z'` in the redo branch, matching the file's other
Shift chords. Affected: `static/js/editor/keyboard-shortcuts.js`.
