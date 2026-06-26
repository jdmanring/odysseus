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
| E1 | 4 built-in MCP servers eagerly spawned at launch; 3 are feature-gated/cold | footprint | **Med–High** | Med | Med | **None** |
| E2 | Host process **content-driven high-water mark** (657→934 MB under use, idle-flat, partial reclaim) — in-proc GPU not reclaimed by renderer purge | footprint | **Med (bounded)** | Med | Med | None |
| E3 | uvicorn `--access-log` writes one log line per HTTP request (D2 polls feed it) | CPU/IO churn | Low | Low | Low | None |
| E4 | uvicorn backend 216 MB private — eager import of full `src/` + heavy deps | footprint | Low–Med | Med | Med | None |

---

## A — Image / media memory (the dominant category for this app)

For a gallery + photo-editor + email-attachment app, **decoded bitmaps are very likely
the single largest renderer-memory category** and the clearest "grows as you use it"
axis. A 4000×3000 photo is ~48 MB decoded regardless of file size.

### A1 — Off-screen images decode eagerly  *(partly superseded — see correction)* — ✅ DONE (#98)

> **Implemented** in `perf/image-lazy-decode` (#98): `loading="lazy"` + `decoding="async"`
> on the document page-stack and gallery draft-thumb renderers. Narrower than the raw
> count suggested — gallery main grids were already lazy and chat images are virtualized.
>
> **Correction (upstream #4852):** the "headline gallery win" framing was wrong. Upstream
> #4852 shows the real gallery-grid cost is that each *visible* tile downloads + decodes
> the **full-resolution original**, which client-side `loading="lazy"`/`decoding="async"`
> *cannot* fix (the bytes still transfer + decode). The proper fix is **server-side cached
> thumbnails** (~400px WebP; cf. Immich) — not done here. #98's real value is the
> **document multi-page PNG stack** (a client-side win #4852 doesn't cover); its
> gallery-draft-thumb part is harmless but marginal. Treat #4852 as the primary
> gallery-memory fix.

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

### A2 — Editor undo snapshot peak  *(reviewed — premise corrected)* — ✅ DONE (#99)

> **Implemented** in `perf/editor-undo-compress` (#99): gzip-compress snapshots
> outside a 3-deep raw window in idle, decode on demand for deep undo. Codec is
> **gzip not PNG** (PNG-via-canvas premultiplies alpha → partial-alpha drift; gzip
> is byte-exact, verified live). Recent undo stays sync; deep undo async + race-
> guarded. Smoke-tested (4 edits + crop). The "lower the caps" option below was the
> safe fallback; compression was chosen to keep full undo depth.

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

## E — Process stack (backend / host / MCP)

*This section is **measured**, not a static survey. Numbers are PSS and Private from
`/proc/<pid>/smaps_rollup` on a live idle session (2026-06-25). PSS (proportional set
size) splits shared copy-on-write pages fairly across sharers; **Private** is what you
actually reclaim by stopping a process. RSS is reported too — note how badly it
double-counts.*

| Process | RSS | PSS | Private | Verdict |
|---|---|---|---|---|
| `qt_wrapper.py` host (browser+GPU+net+tracing, in-process) | 674 | 556 | 495 | **Elephant; mostly private; growth unmeasured (E2)** |
| QtWebEngineProc `--type=renderer` | 281 | 240 | 213 | Already bounded this cycle (reclaim slate) |
| QtWebEngineProc `--type=zygote` ×2 | 68 + 68 | 18 + 24 | 0.9 + 13.5 | **Nearly free — shared COW fork templates. Leave alone.** |
| uvicorn `app:app` backend | 240 | 220 | 216 | Large, mostly private (E3/E4) |
| `email_server` (MCP) | 73 | 56 | 53 | Cold unless email used (E1) |
| `memory_server` (MCP) | 67 | 50 | 48 | **Hot — persistent memory; keep eager** |
| `image_gen_server` (MCP) | 67 | 50 | 48 | Cold unless image-gen used (E1) |
| `rag_server` (MCP) | 67 | 50 | 48 | Cold unless RAG used (E1) |

**Stack total ≈ 1.26 GB PSS.** The two zygotes the user sees as "small" are confirmed
small (PSS 18/24 MB, ~all shared) — correct intuition; not a target.

### E1 — Built-in MCP servers eagerly spawned at launch

**Evidence:** `src/builtin_mcp.py:128` `register_builtin_servers` loops `_BUILTIN_SERVERS`
(`image_gen`, `memory`, `rag`, `email`) and `asyncio.create_task(_connect_python_server(...))`
for **all four** unconditionally at startup (`app.py:980`). Each is a full venv interpreter
with its own imports — **~48–53 MB private each** (measured; they share little heap because
imports land in each interpreter's own heap, not shared `.so` pages).

**Why it matters:** `memory_server` is genuinely hot (persistent memory, every session).
But `email`/`rag`/`image_gen` are **feature-gated** — only exercised if the user opens email,
runs a RAG query, or generates an image. For a typical session that's **~150 MB private
resident for features that may never be touched**.

**Fix (with cautions):** lazy-connect the three cold servers on first tool-call demand —
`src/mcp_manager.py` already has `connect_server`, so the manager can spawn on first use of a
tool that routes to that server. Keep `memory` eager. **Cautions:** (1) `task_scheduler` /
background jobs can invoke tools without UI interaction — deferral must key off *actual tool
demand*, not UI panel state, or a scheduled email task breaks. (2) First-use latency = one
interpreter spawn + import (~hundreds of ms) — acceptable for a user-initiated email/image
action, surface a "starting…" state. (3) Optional idle-unload (stop a server unused for N
minutes) reclaims more but adds re-spawn latency — defer unless measured worthwhile.

### E2 — Host process: partially-reclaimed content-driven high-water mark (MEASURED 2026-06-25)

**Composition:** there is **no separate `--type=gpu` process** (`ps` confirms) — GPU/compositor
runs *in* the host, alongside `NetworkServiceInProcess2` + `TracingServiceInProcess` (per the
renderer's `--enable-features` flags). That explains the large host baseline.

**Gate run (host `VmRSS` telemetry + 30 s `/proc` sampler, single heavy session):**

| Phase | Host VmRSS | Behaviour |
|---|---|---|
| Fresh, idle | **657 MB** | flat (delta ≈ 0) |
| Open all panels (first time) | 657 → **867 MB** | +210 MB step |
| Continued heavy use (~10 min) | 867 → **934 MB** | spikes (+56/+33/+27 MB) **interleaved with real reclaim** (−50/−22 MB); growth **decelerating** |
| Stop interacting | **934 MB, flat** | 5+ consecutive ticks at `delta=+0` |

**Verdict — neither of the two hypotheses; the third:**
- **Not a flat fixed baseline** — it grew **657 → 934 MB (+277 MB, +42%)** with use.
- **Not a runaway / idle leak** — idle is **flat at both ends** (657 fresh, 934 after); reclaim
  is active (large negative deltas); growth **decelerates toward a plateau**.
- It is a **partially-reclaimed, content-driven high-water mark**: the in-process GPU/compositor
  allocates buffers for peak content complexity and holds most of them. The renderer
  `forciblyPurge` reclaim (already landed) does **not** touch host-side GPU memory, so the host
  floor ratchets up to a complexity ceiling and stays there. Bounded (rock-solid in the
  sawtooth sense), but the resting floor after heavy use is ~40% above fresh.

**Severity: Medium, bounded — not a leak, not a blocker.** Does not climb while idle, so it
won't OOM a left-open session. The lever is host/GPU-side, distinct from the renderer reclaim:
Chromium GPU-memory flags (bound the command-buffer / transfer-buffer / tile cache), or the
`--in-process-gpu` vs separate-GPU-process trade-off (separate process = the high-water lives in
a killable/evictable process, at the cost of an IPC hop). **Open a separate follow-up issue**;
do not fold into the renderer reclaim work. Caveat: the controlled *repeat-identical-cycle* test
(does the floor rise on identical repeats, or only on new content?) was not cleanly isolated —
the deceleration + idle-flat strongly indicate a complexity ceiling, but a long-session re-check
would firm up "ceiling" vs "very slow ratchet."

### E3 — `--access-log` writes one line per HTTP request

**Evidence:** `qt_wrapper.py:165` launches uvicorn with `--access-log`; the D2 always-on polls
(email 60 s, tasks 30 s, calendar 30 s) each generate a request → a formatted log line → a
buffered write, **forever, even when idle/backgrounded**. The access log and the D2 polls are
the same churn viewed from two ends.

**Fix (DONE — #113):** ⚠ correction — uvicorn's `access_log` **defaults to ON**, so dropping
the `--access-log` flag alone does nothing; the embedded launch must pass **`--no-access-log`**
explicitly. Applied to all three platform wrappers (qt/mac/windows); startup banners and
tracebacks still reach `server_access.log` via the subprocess stdout/stderr, and errors surface
via `server.log`. Guarded by `tests/test_wrapper_no_access_log.py`. Pairs naturally with the D2
visibility-gating fix. Trivial, zero aesthetic impact.

### E4 — uvicorn backend baseline (216 MB private)

**Evidence:** the FastAPI app eagerly imports the full `src/` surface at module load
(`app.py` top-level `from src... import` chain) plus heavy third-party deps. 216 MB private is
the cost of that import graph resident for the whole session.

**Fix (low priority, med effort/risk):** defer heavy optional imports (ML/embedding/HTTP
stacks) behind first-use inside their route handlers, the same lazy-import discipline as B1 on
the JS side. Med risk because import-time side effects can hide ordering assumptions — needs
care and is the least urgent item here.

---

## Diagnostics added to gather more information (2026-06-25)

A short audit of the existing testing/logging found two measurement gaps that block
ranking the E findings — so the gaps were closed before any fix. *Measure first.*

| What was missing | Added | Lets us answer |
|---|---|---|
| Host-process RSS was never logged — `[MEM]` tracked only the renderer | **Host VmRSS line** in `_log_renderer_memory` (`qt_wrapper.py`), with a per-sample delta — issue #112 | **E2:** is the 556 MB host a fixed baseline or climbing? |
| The whole-stack PSS survey was a one-off, by-hand `smaps_rollup` read | **`mem-probe.py stack`** subcommand (read-only /proc, no CDP needed) | **E1/E4:** cold-MCP footprint and backend growth, repeatably |

**Tests added** (static + smoke, no live app needed): `tests/test_host_rss_telemetry.py`
(5 guards: tracking cell, `/proc/self` read, host line emitted, delta reported, host vs
renderer pid distinct); `tests/test_mem_probe_cli.py` extended (+2: `stack` runs without CDP,
`main()` short-circuits before building CDP). The read-only invariant test already guards that
`stack` cannot mutate live page state.

**How to use them to gather data:**
1. Run a heavy-use session; `grep '\[MEM\] host' logs/wrapper_system.log` → watch the deltas.
   Sustained positive deltas that the renderer purge does not reclaim = host-side growth (E2).
2. `python tooling/mem-probe.py stack` at session start and after an hour → diff the MCP rows
   to confirm the cold servers (E1) stay resident-but-idle, and the backend/host PSS trend (E4).

**Logging hygiene note (not yet a finding):** `[MEM]`/`[CDP]` lines print on every tick
unconditionally. If the host VmRSS turns out flat, consider down-sampling the steady-state
lines (log on change / Nth tick) to keep `wrapper_system.log` churn low — consistent with the
E3 access-log reasoning. Defer until E2 data says whether per-tick host logging is worth it.

---

## Upstream alignment & external validation (researched 2026-06-25)

Findings cross-checked against the upstream repo (`pewdiepie-archdaemon/odysseus`:
issues, discussions, ROADMAP) and Qt/Chromium primary docs. Performance work is an
**actively welcomed** upstream direction, and several findings map onto open upstream items
— which means they are contribution-worthy, not fork-local quirks.

**Upstream items this audit maps onto:**

- **#3276 — "Proposal: Performance Update for Front-end part"** *(open)*. Upstream explicitly
  worries about front-end weight (`static/js` 5.6 MB, `static/style.css` 1 MB+) *specifically
  for non-localhost / Raspberry / remote-host deployment*. This is the natural **umbrella for
  the A/B/C/D front-end findings**. ⚠️ **Strategic caveat:** the proposal floats a possible
  React/Vue front-end framework + a bundler/minifier step. If upstream adopts a bundler, the
  B1 "eager module load" finding is partly subsumed by code-splitting; if it adopts a
  framework rewrite, fine-grained CSS/JS micro-fixes (C2/C3/D1) risk being mooted. **The E
  process-stack findings are framework-independent and carry no such risk.**
- **#2140 — "Docker startup can block UI while initializing local embeddings/RAG"** *(open)*.
  Directly validates **E1/E4**: eager initialization of heavy subsystems at startup is an
  *acknowledged upstream pain point*. Lazy/deferred init is wanted, not novel.
- **#3824 — "manage_mcp does not dynamically disconnect/reconnect live MCP servers"** *(open)*.
  Dynamic MCP lifecycle is a known upstream gap. **E1's lazy-connect-on-demand** intersects
  this — a fix here should be designed to also satisfy dynamic (re)connect, not fight it.
- **ROADMAP — "Email performance audit"** item. `email_server` is one of the cold MCP servers
  in **E1**; deferring it aligns with an item already on the roadmap.
- **Discussion #4879 — "Constant Crashes"**; **#2744 — orphaned `llama-server` holding
  port/VRAM** *(closed)*. Corroborating user-facing symptoms that unbounded
  memory/process growth is a real, reported problem class — not a fork-only concern.

**Qt/Chromium primary-source validation of E2:**

- Qt's own debugging docs confirm GPU runs as an **in-process thread**
  (`Chrome_InProcGPUThread`) in the application/browser process when hardware-accelerated;
  when unavailable, renderers fall back to Skia software raster copied to the browser process
  via shared memory. This **confirms the 556 MB host composition** (in-process GPU + the
  `NetworkServiceInProcess2` / `TracingServiceInProcess` features in our launch flags), and
  means host-side levers are documented Chromium flags (`--in-process-gpu`,
  `--single-process`, network-service placement) — to be weighed only *after* E2's
  growth measurement, since each trades isolation/sandbox for footprint.

*Sources:* [Qt 6 WebEngine Debugging & Profiling](https://doc.qt.io/qt-6/qtwebengine-debugging.html),
[QtWebEngine/Rendering wiki](https://wiki.qt.io/QtWebEngine/Rendering),
upstream issues [#3276](https://github.com/pewdiepie-archdaemon/odysseus/issues/3276),
[#2140](https://github.com/pewdiepie-archdaemon/odysseus/issues/2140),
[#3824](https://github.com/pewdiepie-archdaemon/odysseus/issues/3824).

---

## Scope / honesty notes

- **Static survey only** — no live heap/CPU profiling. Impact estimates are reasoned from
  patterns, not measured. The image findings (A1/A2) in particular deserve a live
  `Memory.getDOMCounters` + GPU-memory check to size them.
- **Now audited (section E, measured PSS):** Python/uvicorn backend, host process, and MCP
  server footprint. **Still open:** host-process growth-over-time (E2) is the one blocking
  measurement — it gates whether the 556 MB host is baseline or a second leak.
- **Still not audited:** font loading/subsetting; the full `editor/` filter pipeline beyond
  the undo/layer signal; WebGL/WebGPU usage.
- **Already addressed (not re-listed):** the large memory-fix slate in `active-work.md`.
- Recommended order: **A1 (cheap, high) → A2 review → B1 (gated) → C1/C3 → C2/#92 → D\***.
