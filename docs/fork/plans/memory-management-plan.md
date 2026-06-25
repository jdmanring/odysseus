# Memory management plan (all layers)

Execution plan for the architecture in `docs/fork/memory-management-architecture.md`.
That doc has the measured diagnosis and the why; this is the sequenced work.

Principle: the renderer accumulates reclaimable memory that QtWebEngine never
evicts (no OS pressure signal). Defend in three layers, weighted by measured
leverage: reclaim first (largest, smallest change), then residency, then keep
paint discipline as a standard. Each item is upstream-candidate, issue-first,
and (because the Qt wrapper is fork-developed) the wrapper items stack on the Qt
native-app feature branches.

## Layer 3 — reclaim (highest leverage, in progress)

**Issue #106. Branch `perf/renderer-memory-reclaim` (stacked on
`feat/qt-native-linux-app`). Implemented.**

- Replace the no-op `simulatePressureNotification('critical')` with
  `Memory.forciblyPurgeJavaScriptMemory` via a gated `_purge_renderer`: RSS
  ceiling (1.8 GB), rate limit (15 s), fired only on mouse-idle and focus-loss,
  run in the CDP executor. Periodic timer becomes telemetry only.
- Tests: `tests/test_qt_cdp_listener_audit.py` updated (64 pass).
- **Verification pending (needs app restart):** restart the app, open several
  panels, and watch `logs/wrapper_system.log` for
  `[MEM] forcible purge (mouse-idle): ok RSS X -> Y kB (delta=-N kB)` with a
  large negative delta once RSS passes the ceiling, and confirm the renderer
  stops climbing without a stutter during active use.
- **Follow-up — platform parity:** mirror the same swap to `mac_wrapper.py`
  (branch `feat/qt-native-mac-app`) and `windows_wrapper.py`
  (`feat/qt-native-windows-app`). Same no-op applies on all QtWebEngine
  platforms. Separate issues, one per platform branch.
- **Tuning to confirm in-app:** ceiling (1.8 GB) and interval (15 s). If idle
  reading still stutters too often, raise the ceiling; if memory still peaks too
  high, lower it. These are the two knobs.

## Layer 2 — residency (unload, do not just hide)

Panels currently `classList.add('hidden')` and stay fully resident. With many
open, all DOM, observers, timers, and decoded images live at once. Adopt the
browser tab-discarding pattern: a panel not in front releases its resources and
rebuilds when shown.

Proposed issues / branches (from `upstream-mirror`):

1. **Modal teardown-on-close hook.** One lifecycle hook in `modalManager.js` so a
   panel can register a teardown (clear container, stop timers, disconnect
   observers) run on close (or after a hidden TTL), and a rebuild on next open.
   Opt-in per panel so nothing breaks silently.
2. **Apply teardown to the heaviest panels first** (measured node counts):
   `doclib-modal` (4244), `cookbook-modal` (2978), `settings-modal` (2835).
3. **Virtualize the remaining long lists** the way chat history already is:
   memory, email, doclib, tasks. Off-screen rows then hold no DOM or tiles.
4. **Timer/observer hygiene:** every panel that starts a `setInterval`,
   `ResizeObserver`, or `IntersectionObserver` must stop it on teardown. Audit
   the modules found polling (tasks, cookbookRunning, sessions, emailInbox).

Sequence: 1 then 2 then 3 then 4. Each lowers the ceiling the reclaim must fight
and cuts how often the purge fires.

## Layer 1 — paint discipline (standing standard, not a project)

Already largely done (compositor-promote animations, `content-visibility`,
remove the raster-tint flag, fix listener leaks). The 2026-06-25 measurement
showed this layer has hit diminishing returns for the multi-panel case (pausing
every animation did not change the slope). Keep as a review standard:

- animate only `transform` / `opacity`; never `background`, `box-shadow`,
  `filter`, gradient stops, or typed custom properties on many elements,
- pause decorative animation when its panel is not foreground,
- question whether perpetual decorative animation (for example the per-item
  memory "synapse sweep", ~21 infinite animations) earns its cost; prefer
  on-interaction or one-shot effects. **Aesthetic decision for the user:** keep
  source-faithful look, so pause-when-not-foreground rather than remove, unless a
  given effect is measurably expensive.

## Instrumentation (parallel, ongoing)

- Keep logging renderer VmRSS + DOM counters periodically (already present) so
  regressions show as a slope.
- The CDP slope-test method used in the diagnosis (attach to port 9222, read RSS
  rate before/after an intervention) is the standard way to **prove a producer
  before fixing it**. Do not optimize a producer that the slope test does not
  implicate.
- Track a renderer RSS ceiling as a product requirement (usable on modest
  hardware), not just a nice-to-have.

## Sequencing summary

1. Land Layer 3 (#106) and verify in-app, tune the two knobs. Mirror to mac /
   windows.
2. Layer 2.1 (teardown hook) + 2.2 (heaviest three panels).
3. Layer 2.3 (virtualize lists) + 2.4 (timer/observer hygiene).
4. Layer 1 stays a review standard; revisit perpetual animations only if the
   slope test implicates them.

## Open decisions (user)

- Reclaim knobs: ceiling 1.8 GB, interval 15 s — adjust after watching it run.
- Residency aggressiveness: teardown immediately on close, after a hidden TTL, or
  only under RSS pressure.
- Aesthetics: pause-when-not-foreground (source-faithful, chosen default) vs
  removing perpetual decorative animation.
