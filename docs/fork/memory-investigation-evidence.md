# Memory investigation — evidence ledger (2026-06-25)

This is the proof behind the memory/CPU work. Every claim here was measured on the
running app via the Chrome DevTools Protocol (CDP) endpoint the wrapper exposes at
`http://localhost:9222`, or read from `/proc/<pid>/status`. Nothing here is
inferred without a measurement. If a future reader doubts a claim, the "method"
lines say exactly how to reproduce it.

Companion docs: `memory-management-architecture.md` (the strategy),
`plans/memory-management-plan.md` (the sequenced work), `memory-explosion-research.md`
(earlier chat/agent-session findings).

## Method (how every number below was taken)

- CDP is live whenever the app runs: `qt_wrapper.py` passes
  `--remote-debugging-port=9222`. List targets: `GET http://localhost:9222/json`.
  The page target's `webSocketDebuggerUrl` accepts `Runtime.evaluate`,
  `Memory.getDOMCounters`, `Memory.forciblyPurgeJavaScriptMemory`, etc.
- Renderer RSS: read `VmRSS` from `/proc/<renderProcessPid>/status`.
- CDP `Runtime.evaluate` returns `{result:{result:{value}}}` (two `result`
  levels) — a parsing slip on the inner level produced false `None`s mid-session;
  the corrected reads (verified with `2+2 -> 4`) are the ones recorded here.

## 1. The footprint is renderer-side reclaimable cache, not a JS leak

| Measurement | Value | Method |
|---|---|---|
| Renderer RSS (panels open, idle) | 5.1–6.4 GB and climbing | `/proc/<pid>/status` VmRSS |
| JS heap used / total / limit | **43 / 45 / 527 MB** | `performance.memory` via CDP |
| DOM counters | nodes **123,351**, documents 4, listeners 4,578 | `Memory.getDOMCounters` |
| Live main-document nodes | **17,534** | `document.getElementsByTagName('*').length` |
| Decoded images | ~47 MB | sum of `naturalWidth*naturalHeight*4` |
| Canvases | 0 MB | `document.querySelectorAll('canvas')` |

The ~106k gap between `getDOMCounters` nodes (123k) and live DOM (17.5k) is
detached/transient nodes. JS heap is two orders of magnitude too small to be the
footprint. Conclusion: the GBs are renderer cache (raster tiles, transfer buffers,
transient Oilpan), not JavaScript objects.

## 2. It is reclaimable; the wrapper's reclaim call was a no-op

| Call | RSS before -> after | Verdict |
|---|---|---|
| `Memory.simulatePressureNotification('critical')` | 4861 -> 4884 MB | **no-op on QtWebEngine** |
| `Memory.simulatePressureNotification('critical')` (retest) | unchanged | no-op |
| `Memory.forciblyPurgeJavaScriptMemory` | 6425 -> **1179** MB | reclaims **5.2 GB** |
| `Memory.forciblyPurgeJavaScriptMemory` (retest) | 4884 -> **1141** MB | reclaims **3.7 GB** |

The wrapper's idle/periodic/focus-loss triggers all called the no-op
(`simulatePressureNotification`), and `gc()` only collects the 43 MB JS pool, so
the renderer climbed unbounded despite the existing infrastructure. Fix: issue
#106 — replace with `forciblyPurgeJavaScriptMemory`, gated.

## 3. Per-process: the renderer is the one that grows

15-second sample, `/proc/*/status` filtered to `QtWebEngineProc`:

```
   pid type               RSS MB   Δ MB/s
  5236 renderer             2927      3.5
  5213 zygote                121      0.0
  5214 zygote                121      0.0
```

The renderer holds and grows the memory; other processes are flat.

## 4. The idle climb has two producers (cancel-test, read slope not level)

App idle, ~10 panels open, zero input:

| Condition | RSS slope | Inference |
|---|---|---|
| Baseline (24 CSS animations running) | ~5.0 MB/s | — |
| All CSS animations cancelled (verified 0 running) | ~3.1 MB/s | animations ≈ **1.7 MB/s** |
| All `setInterval`/`setTimeout` cleared | unchanged (~3.3 MB/s) | not a timer |
| All panels hidden | unchanged | not panel compositing per se |
| Visible `backdrop-filter` elements | **0** | ruled out |

Method: `document.getAnimations().forEach(a=>a.cancel())` then re-sample RSS over
15 s. Two distinct producers: ~1.7 MB/s CSS animations + ~3.1 MB/s non-animation.

## 5. The non-animation producer named directly: a leaked whirlpool spinner

Read-only `requestAnimationFrame` wrap for 1 s, counting scheduler call sites by
stack (creates/cancels nothing):

```
rAF schedulers over 1s (count <- stack):
    43  at Spinner._drawWhirlpool (static/js/spinner.js:256) <- spinner.js:256
```

Plus: **0 canvas elements in the DOM** at the same moment. A whirlpool spinner was
scheduling ~43 frames/second on a canvas that is not in the DOM — an orphaned
spinner looping forever. CSS animations do not create DOM nodes and `clearInterval`
does not stop rAF, which is why this survived tests in row 4. This is the ~3.1 MB/s
and the main-thread saturation (CDP `Runtime.evaluate` began timing out under it,
itself a sign of a hot JS loop). Root cause and fix: issue #107.

## 6. The animation producer: ~20 perpetual sweeps on memory rows

| Measurement | Value | Method |
|---|---|---|
| Running CSS animations (Brain panel open) | **24**, 21 on `memory-item` | `document.getAnimations()` grouped by target |
| `infinite` animation declarations in `style.css` | 78 (most state-gated) | `grep -c infinite` |
| Dominant always-on | `memory-synapse-sweep` on `#memory-list .memory-item::after` | source |

`memory-synapse-sweep` is declared `infinite` on every memory row, so it runs
perpetually whenever the panel is open (and was inverted: hidden on hover). This is
the bulk of the ~1.7 MB/s. Fix: issue #108 — hover-triggered, single iteration.

## 7. Fixes shipped (with verification status)

| Issue | Fix | Branch | Verified |
|---|---|---|---|
| #106 | `forciblyPurgeJavaScriptMemory`, gated (RSS ceiling 1.8 GB, 15 s rate limit, off-interaction-path) | `perf/renderer-memory-reclaim` | **In-app: sawtooth confirmed** (user saw memory climb then drop repeatedly after restart) |
| #106 follow-up | periodic sustained-idle reclaim (single-shot re-armed only on mouse move -> filled all RAM on walk-away; now repeating, keyboard-aware) | same | bounds memory; sawtooth is the evidence |
| #107 | whirlpool spinner terminates when never-visible-within-grace or hidden (was unbounded `!_wpWasConnected`) | `fix/spinner-orphan-leak` | source-text tests; in-app re-measure pending |
| #108 | `memory-synapse-sweep` hover-triggered, not perpetual | `fix/brain-panel-oom` | source-text tests; in-app re-measure pending |

Each fix is cherry-picked to `develop` (`-x`). Source-text tests pass
(`test_qt_cdp_listener_audit.py`, `test_spinner_orphan_leak_js.py`,
`test_brain_panel_oom_css.py`). Source-text tests prove the code's shape, not the
runtime; the behavioural proofs are the measurements above and the sawtooth.

## What is still unproven (do not claim otherwise later)

- The exact MB/s attributable to the spinner vs other minor sources after the #107
  fix: needs a fresh live re-measure on next start (the producer is named and
  fixed, but the post-fix slope has not been re-taken).
- The #107 and #108 fixes are verified by tests and reasoning, not yet by a live
  before/after slope. Re-run the row-4 cancel-test and the row-5 rAF capture after
  a restart to confirm the slope drops.

## Lessons learned: the animation cost model + an audit (2026-06-25)

### Why a continuous animation can grow memory (the recurring question)

"Wouldn't it just get cached once?" — correct for *compositor* animations, wrong
for *paint* ones. Three tiers:

- **Compositor (cheap, cacheable):** `transform`, `opacity`. The element is
  rasterized **once** into a layer; each frame the GPU just re-positions or fades
  that one cached texture. Near-zero ongoing cost — fine to loop forever.
- **Paint (expensive, NOT cacheable):** `box-shadow`, `filter`, `background`,
  `background-position`, `color`, `border-color`, `clip-path`, `-webkit-mask`.
  Computed *during rasterization*. Every step of the loop is a different bitmap, so
  there is no single frame to cache — the engine re-rasterizes ~60x/s forever.
- **Layout (worst):** `top`/`left`/`width`/`height`/`inset`. Re-runs layout *and*
  paint every frame.

A normal browser keeps even the expensive tiers bounded (buffers recycled, old
tiles evicted under pressure). On **Qt WebEngine eviction never fires** (no OS
pressure signal — the root defect of this whole investigation), so paint output
**accumulates**. Cost ≈ repaint area × frame rate × persistence. Proof case:
`notes-quick-pulse` animated `box-shadow` on the always-visible ~200×46px
`.notes-quick-add` box → ~200×46×4×60fps ≈ **2.2 MB/s**, matching the measured idle
climb. Fixed by baking the glow into a `::after` layer (rasterized once) and
pulsing its **opacity**.

### Standard (apply going forward)

1. Continuous/`infinite` animations may animate **only** `transform`/`opacity`.
2. If a paint effect must loop, render it on a **pseudo-element rasterized once**
   and animate that layer's opacity (see `.notes-quick-add::after`).
3. Prefer **gating** decorative animation behind state/hover so it is not perpetual.
4. Cost scales with **area** and **persistence**: a paint animation on a large,
   always-visible element is the worst case; on a tiny dot or a transient state it
   is usually fine.

### Audit: are we doing this elsewhere? (checked all 56 infinite animations)

18 animate a paint/layout property. Categorised:

- **Always-on + large (the real cost):** `notes-quick-pulse` only. **Fixed.**
- **State-gated (transient — run only during loading/unread/running/streaming/
  notification, then stop):** `gallery-skeleton-shimmer`, `notes-skeleton-shimmer`,
  `ge-canvas-spin`, `task-log-pulse`, `thread-pulse`, `synapse-travel/-capped`,
  `research-dot-pulse`, `stream-complete-pulse`, `skill-audit-pulse`. Acceptable.
- **State-gated but can persist on small elements (low per-instance cost,
  candidate cleanup):** `cookbook-srv-glow-ok`, `email-card-unread-breathe`,
  `cookbook-notif-pulse`, `research-badge-breathe`, `note-reminder-glow`,
  `rail-notes-badge.fired`. Tiny (dots/badges); convert to opacity-on-pseudo-element
  only if a future measurement implicates one.

Net: the one always-on, large offender is fixed; the rest are transient or tiny.
The standard above plus the brain-panel-oom keyframe tests prevent reintroducing
the always-on case.
