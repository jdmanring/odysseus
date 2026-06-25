# Performance Audit — Memory Footprint, Growth, and CPU (2026-06-25)

A pass-through survey of opportunities to **reduce baseline memory footprint**,
**reduce memory growth with use**, and **reduce CPU/GPU overhead** — under the hard
constraint of **keeping aesthetics as close to source as possible**.

This is a *report*, not an implementation. Each finding is ranked by impact / effort /
risk / **aesthetic-impact** (the binding constraint). Pick what's worth pursuing; each
fix needs its own issue + branch per the fork workflow.

Context: a large slate of renderer-memory fixes already landed this cycle (DOM
virtualization, streaming throttle, GC catch-up + idle GC, listener-leak fixes,
content-visibility, in-place finalize, etc. — see `active-work.md`). This audit targets
what those did **not** cover. Methodology: static survey (grep + read), not live
profiling — impact estimates are reasoned, not measured.

---

## Ranked summary

| # | Finding | Category | Impact | Effort | Risk | Aesthetic Δ |
|---|---------|----------|--------|--------|------|-------------|
| A1 | Off-screen `<img>` decode eagerly (no `loading="lazy"`/`decoding="async"`) | footprint + growth | **High** | Low | Low | **None** |
| A2 | Photo-editor `undoStack` + cached layer `getImageData` grow with edits | growth | **High** (potential) | Med | Med | None |
| B1 | Large modules eager-loaded (`document.js` ~10k LOC, `gallery.js`, `settings.js`) | footprint | Med–High | Med | Med | None |
| C1 | `backdrop-filter` over scrolling/animating content → continuous repaint | CPU/GPU | Med | Med | Low | **None if scoped** |
| C2 | `transition: all` (78 CSS + 15 JS) → specific properties (#92) | CPU | Med | Med | Low–Med | None |
| C3 | Infinite CSS animations running while off-screen/hidden | CPU/GPU | Med | Med | Low | None |
| D1 | `modalManager` 1 s perpetual scan timer | idle power | Low | Low | Low–Med | None |
| D2 | Always-on network polls run regardless of panel visibility | CPU/network | Low | Low | Low | None |
| D3 | `dataUrl` caches (`_sigCache`, `_libListCache`) — base64 in memory, no eviction | growth | Low | Low | Low | None |

---

## A — Image / media memory (the dominant category for this app)

For a gallery + photo-editor + email-attachment app, **decoded bitmaps are very likely
the single largest renderer-memory category** and the clearest "grows as you use it"
axis. A 4000×3000 photo is ~48 MB decoded regardless of file size.

### A1 — Off-screen images decode eagerly  *(headline; aesthetics-neutral)* — ✅ DONE (#98)

> **Implemented** in `perf/image-lazy-decode` (#98): `loading="lazy"` + `decoding="async"`
> on the document page-stack and gallery draft-thumb renderers. Narrower than the raw
> count suggested — gallery main grids were already lazy and chat images are virtualized.

**Evidence:** 26 `<img>` elements created in JS, only 4 set `loading="lazy"`
(`grep "new Image(|createElement('img')"` vs `loading=lazy`). Object-URL hygiene is
otherwise good (28 `createObjectURL` / 31 `revokeObjectURL` — no leak).

**Why it matters:** without `loading="lazy"`, every gallery/email/doc-library thumbnail
decodes into memory as soon as it's attached, even far off-screen — so opening a large
gallery holds *all* decoded bitmaps at once. Without `decoding="async"`, decode also
blocks the main thread (jank on open/scroll).

**Fix (low-risk, zero aesthetic change):** set `loading="lazy"` and `decoding="async"`
on JS-created thumbnail/list images in `gallery.js`, `emailLibrary.js`, `document.js`,
and any list renderer. Off-screen images then decode near-viewport and off-thread.
Pairs naturally with the existing `content-visibility:auto` work.

### A2 — Editor undo snapshot peak  *(reviewed — premise corrected)*

**Investigation result (2026-06-25):** the original "grows linearly / unbounded" framing
is **wrong**. Findings from reading the code:

- Undo is **already capped**: `galleryEditor.js MAX_HISTORY = 20`; `notes.js
  UNDO_LIMIT = 30` (both `shift()` the oldest off). Not unbounded.
- The memory is **editor-session-scoped and freed on editor close** — so this is a
  *transient peak during an active edit session*, NOT the "grows-with-use across the app"
  axis (that was hover-OOM, fixed in #97).
- **Per-step magnitude is the real cost:** `_snapshotState()` captures **every layer's
  full raw `getImageData`** on *every* mutating op (`saveState` runs first in all of
  them). One step = Σ(all layers' full RGBA bitmaps), ×20. Worst case bounded but large:
  4000×3000 × 3 layers × 20 ≈ ~2.9 GB; 2000×1500 × 2 × 20 ≈ ~480 MB. The waste: most
  edits touch one layer, yet unchanged layers are re-stored in every snapshot.

**Why the obvious fix is gone and the clever one is risky:**

- "Cap undo depth" — *already done*. The remaining knob is *lowering* the cap.
- Dirty-flag instrumentation to skip unchanged layers is **not safe here**: ~200 diffuse
  `getImageData`/`putImageData`/`drawImage` sites across a dozen files, no single paint
  chokepoint. Miss one → silent wrong-pixels undo (data loss). A Proxy-wrapped context
  doesn't save it — `canvas.getContext('2d')` returns the same underlying ctx, so any
  site re-fetching it bypasses the wrapper.

**Options (ranked by trade for a footprint pass):**

| Option | Peak win | Cost | Risk |
|--------|----------|------|------|
| Lower `MAX_HISTORY` 20→~12, `notes` 30→~15 | ~40% | fewer undo steps (capability, not aesthetics) | **none** |
| PNG-compress snapshots (lossless) | ~5–10× | undo *latency* (visible, recoverable) | low |
| Structural-share unchanged layers (content-compare) | large | ~100ms stroke-end full-compare; correctness-critical | **high** (silent corruption if the no-in-place-mutation assumption breaks) |

Since the prize is a *bounded, transient, freed-on-close* peak — not a leak — paying
silent-corruption risk for it is a poor trade. **Recommended: lower the caps** (free,
aesthetics-neutral); escalate to PNG-compression only if peak is still a problem.
Structural-sharing is documented but **not recommended** for a footprint pass.

---

## B — Baseline footprint (eager module loading)

### B1 — Large modules loaded at startup despite lazy paths

**Evidence:** 46 eager `<script>` tags in `index.html`; 122k LOC JS total. The biggest
modules are eager even though dynamic-`import()` paths exist for them:
`document.js` (9 952 LOC, editor — eager **and** 3 lazy import sites), `gallery.js`
(eager + 3 lazy), `settings.js` (eager + 1 lazy).

**Why it matters:** every eager module is parsed, compiled, and held at startup whether
or not the user opens that feature — baseline RSS + startup parse CPU on the welcome
screen, where none of editor/gallery/settings is needed.

**Caution (why this is "potential," not confirmed):** `document.js` being *dual*-loaded
(eager + lazy) is a signal it may register globals/handlers at load that other eager
modules depend on. **Gate on a dependency check**: confirm nothing imported at startup
needs it before dropping the eager tag. If clean, lazy-loading the editor alone removes
~10k LOC from the baseline.

---

## C — CPU/GPU during active use

### C1 — backdrop-filter over moving content  *(aesthetics-safe if scoped)*

**Evidence:** 28 `backdrop-filter` occurrences, blur radii up to `blur(24px)
saturate(170%)` (frosted theme).

**Why it matters:** a backdrop-filter must re-sample and re-blur the content behind it
**every frame that content changes**. Over a scrolling chat history or an animating
panel, that's a continuous full-filter repaint.

**Fix (aesthetics-neutral):** audit *which* backdrop-filters sit over scrolling/animating
regions and address those specifically (e.g. isolate the blurred layer so it doesn't
recompute during background scroll). **Do NOT** reduce blur radius (24→12) as a blanket
CPU win — that's a *visible* change to the frosted look and violates the aesthetic
constraint.

### C2 — `transition: all` → specific properties  *(tie to #92)*

**Evidence:** 78 `transition: all` in `style.css` + 15 in JS inline styles. Issue #92
already scopes 4 selectors; this is the broader set.

**Why it matters:** `transition: all` makes *any* property change (including
layout/paint props touched on hover) animate through non-compositor frames.

**Fix:** replace with the specific properties actually intended to transition. Aesthetics
are identical (same visible transitions). **Per-site judgment, not a global find-replace**
— some sites legitimately transition multiple props; medium effort. Roll into #92.

### C3 — Off-screen infinite animations

**Evidence:** 78 `infinite` animations in `style.css`. The Brain/Notes panel pass
(`fix/brain-panel-oom`) paused some via `animation-play-state`, but coverage is partial.

**Why it matters:** an `infinite` animation on a hidden/off-screen element still consumes
CPU/GPU each frame.

**Fix:** identify which infinite animations run while their container is hidden/off-screen
and gate them with `animation-play-state: paused` (or `content-visibility`). **Counting 78
is not yet a finding** — the actionable step is identifying the hidden-but-animating
subset first.

---

## D — Minor / power

### D1 — `modalManager` 1 s perpetual scan  *(idle-power, not a CPU headline)*

**Evidence:** `modalManager.js:1472 const _scanTimer = setInterval(_scanAndWire, 1000)`
runs forever; `_scanAndWire` calls `getElementById` + idempotent `injectMinimizeButton`
for each auto-wire modal. `injectMinimizeButton` early-returns when already wired
(`modalManager.js:1364`), so nearly every tick is wasted.

**Why it matters:** per-tick cost is microseconds (a few `getElementById`s) — *not* a CPU
win. The real cost is that a perpetual 1 s timer **prevents renderer idle quiescence**
(battery/power on laptops/tablets).

**Fix (with a caution):** replace polling with the modal-open event the app already emits,
**or** a `MutationObserver` — but scope it to the modal root's direct children
(`childList` only). A `subtree` observer on `document.body` would fire thousands of times
during chat streaming, which is *worse* than the poll. Frame as idle-power cleanup.

### D2 — Always-on polls ignore visibility

**Evidence:** `emailInbox.js:199` unread refresh every 60 s; `tasks.js:2716` notif poll
30 s; `calendar.js:3287` tick 30 s — all module-scope, running regardless of whether the
panel is open or the tab is visible.

**Fix:** gate on `document.visibilityState === 'visible'` and/or panel-open state. Small
CPU + network savings; keeps wakeups out of the idle/background path.

### D3 — base64 dataUrl caches without eviction

**Evidence:** `document.js:1067 _sigCache = new Map()` stores signature `dataUrl`s (base64,
~33% larger than binary); `emailLibrary.js:678 _libListCache = new Map()`. Bounded by
domain data size, no LRU.

**Fix:** add a small LRU cap. Low impact (counts are small), but base64 image strings are
memory-heavy per entry.

---

## Scope / honesty notes

- **Static survey only** — no live heap/CPU profiling. Impact estimates are reasoned from
  patterns, not measured. The image findings (A1/A2) in particular deserve a live
  `Memory.getDOMCounters` + GPU-memory check to size them.
- **Not audited:** Python/uvicorn backend memory; font loading/subsetting; the full
  `editor/` filter pipeline beyond the undo/layer signal; WebGL/WebGPU usage.
- **Already addressed (not re-listed):** the large memory-fix slate in `active-work.md`.
- Recommended order: **A1 (cheap, high) → A2 review → B1 (gated) → C1/C3 → C2/#92 → D\***.
