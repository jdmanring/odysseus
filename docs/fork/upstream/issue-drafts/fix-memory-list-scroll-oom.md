# Upstream Issue Draft: fix-memory-list-scroll-oom

**File on:** `odysseus-dev/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/fix-memory-list-scroll-oom.md`
**Branch:** `fix/memory-list-scroll-oom`
**Type:** Bug / Performance

---

## Title

`[Brain] Scroll-hover transition on memory list produces unbounded raster-tile growth`

---

## Body

**Install method:** Docker / manual Python / Qt wrapper

**OS / device:** Linux / macOS / Windows with Qt wrapper (most visible in embedded Chromium)

**Summary:**

Moving the cursor up and down over the Brain memory list causes continuous RSS growth. Approximately 1 GB of growth is reproducible from repeated scroll passes over a list of 20+ memories.

**Root cause:**

The base `.memory-item` class sets `transition: all 0.15s`. As the cursor passes over items during scroll, each item cycles through enter-hover and leave-hover state, transitioning `background` and `border-color` (from `.memory-item:hover`). Neither property is compositor-promoted; each transition requires main-thread painting for approximately 9 frames at 60 fps. Qt does not forward OS memory pressure to the embedded Chromium renderer; the compositor's tile manager never receives eviction signals, so raster tiles deposited by these transitions accumulate without bound.

**Expected behavior:**

Scrolling the memory list without clicking should not produce measurable RSS growth.

**Observed behavior:**

Repeated up-down scroll passes over the memory list grow RSS by roughly 1 GB. The growth is continuous and does not plateau.

**Reproduction:**

1. Open the Brain panel with 20+ memories visible.
2. Move the cursor slowly over the memory list, up and down, for 60 seconds without clicking.
3. Check RSS via `ps aux` or Activity Monitor. Growth of several hundred MB confirms the issue.

**Fix:**

Override `transition: all 0.15s` in the `#memory-list .memory-item` context with `transition: opacity 0.15s`. Background and border-color changes in this context take effect instantly rather than depositing raster tiles per frame. `opacity` is compositor-promoted and safe to transition without main-thread paint.

---
