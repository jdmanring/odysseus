# PR Draft: perf/editor-undo-compress -> odysseus-dev/odysseus:dev

**Branch:** `perf/editor-undo-compress`
**Status:** Ready to file
**Base:** cut from `upstream-mirror`, 3 files, +372

---

## Title

`perf(editor): compress image-editor undo snapshots`

---

## Summary

### Problem

Each editor undo snapshot holds a full-canvas `ImageData` - four bytes per pixel,
uncompressed, per step. The undo stack therefore grows in raw bitmap terms, which
on a large canvas is tens of megabytes for a handful of edits.

### Fix

gzip the snapshot buffer (`_compressSnap` / `_decompressSnap`) via the platform's
own compression streams. No new dependency.

### Why gzip rather than PNG

PNG is the obvious alternative and it is **wrong here**: encoding through a canvas
premultiplies alpha, so a round-trip through PNG is **lossy for partial-alpha
pixels**. An undo step that silently alters semi-transparent pixels is a
correctness bug in an image editor, not a performance trade.

gzip operates on the raw buffer and is exactly lossless, which is the property
the undo stack requires.

---

## Verification

**10 passed, 1 skipped**, measured 2026-08-03.

The skip is deliberate and worth explaining, because it is the more meaningful
test. `tests/test_editor_undo_compression_integration.py` exercises the **real
codec path in a real browser** over CDP: `getImageData` -> gzip -> gunzip -> new
`ImageData` -> `putImageData` -> `getImageData`, asserting **byte-identical
pixels** for three cases chosen to break it - photo noise, **partial alpha** (the
PNG-premultiply danger case above), and a fully transparent layer.

It skips when no CDP endpoint is available, and the branch gates the live-session
suite behind `ODYSSEUS_LIVE_UI_TESTS=1` so it neither hangs nor fails spuriously
on CI or on a machine without the app running.

**Not covered:** the editor's async undo/redo orchestration, which needs live UI
driving. The codec is proven lossless; the surrounding state machine is not
covered by this PR and that should not be inferred from the test count.

---

## Scope

`static/js/galleryEditor.js` (+116) and two test files.
