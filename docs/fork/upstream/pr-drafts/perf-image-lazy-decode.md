# PR Draft: perf/image-lazy-decode -> odysseus-dev/odysseus:dev

**Branch:** `perf/image-lazy-decode`
**Status:** Ready to file
**Base:** cut from `upstream-mirror`, 3 files, +52/-1

---

## Title

`perf(ui): lazy-decode off-screen document pages and gallery draft thumbs`

---

## Summary

### Problem

Off-screen images in stacked and grid layouts decode into memory eagerly. A
multi-page document renders as a tall vertical stack of full-page PNGs, so
**every page decodes at once** on open; the gallery draft grid renders many
off-screen thumbnails the same way.

Decoded bitmap size is unrelated to file size, so a modest PNG can occupy a large
multiple of its bytes once decoded, times the page count, for pages the user has
not scrolled to.

### Fix

Add `loading="lazy"` and `decoding="async"` to those two surfaces, so images
decode near-viewport and off the main thread.

**Deliberately narrow, and the exclusions are the design:**

- gallery **main** grids are already lazy
- chat images are DOM-virtualized, so they are already bounded
- focus, detail and lightbox images stay **eager** — lazy there would defer the
  image the user just clicked, which is the one image that must not wait. That
  exclusion is guarded by a test rather than left to convention.

### No aesthetic change

`loading="lazy"` only defers images that are off-screen; `decoding="async"` moves
decode off the main thread without changing what is painted. Neither introduces a
placeholder or a layout shift.

---

## Verification

**4 passed**, measured 2026-08-03: source guards asserting the attributes on the
two intended surfaces and their **absence** on focus/detail/lightbox.

---

## Scope

`static/js/document.js` (+5), `static/js/gallery.js` (1 line), one test file.
