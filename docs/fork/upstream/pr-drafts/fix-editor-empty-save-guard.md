# PR Draft: fix/editor-empty-save-guard → odysseus-dev/odysseus:dev

**Branch:** `fix/editor-empty-save-guard`
**Fork issue:** [#101](https://github.com/jdmanring/odysseus/issues/101)
**Status:** Single clean commit. File the upstream issue first, fill `Fixes #___`, then open the PR.

## Upstream PR title
`fix(editor): guard editor save against a 0-byte / broken gallery image`

## Summary

### Problem
Both gallery-editor save paths — `ge-save` (replace) and `exportToGallery` (save-copy)
— flatten to a canvas of `state.imgWidth × state.imgHeight` and upload with no guard
against an empty result. When those dimensions are `0`/unset (a save firing before
the image loaded, or after a state reset), the upload writes a broken **0-byte**
gallery entry (observed live: `null × null`, 0 bytes).

### Fix
- `_flattenForSave()` — a shared flatten that throws on a 0×0 canvas; used by both
  save paths so neither can upload an empty image.
- Reject an empty/trivial blob in `toBlob` so an empty encode never uploads.
- The existing `catch` surfaces the failure as an error toast instead of silently
  writing a broken entry.

## How to Test
1. Open a gallery draft in the editor.
2. Trigger a save before the image has finished loading (or after resetting editor
   state) — e.g. rapid open-then-save.
   - **Expected:** the save is rejected with an error toast; no gallery entry is written.
   - **Before this fix:** a 0-byte, unopenable image (`null × null`) appears in the gallery.
3. Normal edit → save still writes a valid image.

### Tests
`tests/test_editor_empty_save_guard.py` — `_flattenForSave()` throws on 0×0; the
`toBlob` empty-blob reject fires; both save paths are guarded.

## Scope
One file (`static/js/galleryEditor.js`). No change to normal (non-empty) saves.

## Target branch
`dev` (never `main`).

## Fixes
`Fixes #___` (fill with the upstream issue number after filing).
