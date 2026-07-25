# Upstream Issue Draft: fix-editor-empty-save-guard

**File on:** `odysseus-dev/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/fix-editor-empty-save-guard.md`
**Branch:** `fix/editor-empty-save-guard`
**Type:** Bug

## Title
`fix(editor): guard editor save against a 0-byte / broken gallery image`

## Body
Both gallery-editor save paths (`ge-save` replace and `exportToGallery` save-copy)
flatten to a canvas of `state.imgWidth x state.imgHeight` and upload with no guard
against an empty result. If those dimensions are `0`/unset (a save firing **before
the image finished loading**, or **after a state reset**) the upload writes a broken
**0-byte** gallery entry (observed live: `null x null`, 0 bytes).

**Steps to reproduce:** open a draft in the editor and trigger a save before the
image has loaded (or after resetting editor state) -> a 0-byte, unopenable image is
written to the gallery.

**Fix:** add `_flattenForSave()` (throws on a 0x0 canvas), used by both save paths,
plus an empty/trivial-blob reject in `toBlob` so an empty encode never uploads; the
existing `catch` surfaces the failure as an error toast. Affected:
`static/js/galleryEditor.js`.
