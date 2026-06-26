# Memory management architecture (gold-standard approach)

Status: design / proposal. Companion to `memory-explosion-research.md` (chat/agent
session findings) and `perf-audit-2026-06.md`. This doc covers the whole-app
memory strategy, prompted by a multi-panel-open session reaching 5+ GB and
climbing.

## What we measured (2026-06-25, live via CDP on the running app)

Most menu panels open, app idle, renderer climbing:

- Renderer RSS 5.1 GB and rising at roughly 3 to 11 MB/s while idle (rate varies
  with how much is open and recently active).
- JS heap (`performance.memory`): 43 MB used of a 527 MB limit. Tiny. The growth
  is not JavaScript objects.
- `Memory.getDOMCounters`: ~123k to 131k nodes across 4 documents, climbing
  ~100/s, while the live main document held a flat 17,534 nodes. The gap is
  detached / transient nodes pending collection.
- Decoded images ~47 MB, canvases 0 MB. Not the cause.
- Per-process: the **renderer** process holds the memory and is the one growing
  (~3.5 MB/s idle); other QtWebEngine processes are flat.
- `Memory.forciblyPurgeJavaScriptMemory` reclaimed **6425 MB to 1179 MB in one
  call** (a 5.2 GB drop).

Producer discrimination (slope tests, reading rate not level):

- Pausing all CSS animations: no change to the slope.
- Clearing all `setInterval` / `setTimeout`: no change.
- Hiding all open panels: no change.

### Conclusion

This is not a JavaScript leak and not a single rogue widget. It is the renderer
accumulating **reclaimable** memory (raster tiles, decode and transfer buffers,
transient Oilpan allocations) that the engine never evicts on its own. The proof
that it is reclaimable, not leaked, is the single forcible purge recovering
5.2 GB. The exact micro-producer is diffuse main-thread rasterization and was not
pinned to one source; a heap snapshot filtered for detached DOM is the follow-up
to identify it precisely, but it is secondary to the architectural gap below.

## Root cause (platform), and the gap in our current approach

Embedded Chromium evicts these caches when it receives an **OS memory-pressure
signal** (`base::MemoryPressureListener` / `MemoryPressureMonitor`). QtWebEngine
does not forward OS pressure to the renderer, so the listener never fires and the
caches grow until the process is killed. This is a known, long-standing
QtWebEngine limitation (see sources). It is the same root cause already
documented for the chat/agent OOM in `memory-explosion-research.md`; the
multi-panel case is another symptom of the one underlying gap.

Our current reclaim path (`_scheduleIdleGc`, added Session 3 to 4) calls V8
`gc()`. That collects the JavaScript heap, which here is 43 MB. It does nothing
for the multi-GB renderer cache pool. **We are reclaiming the wrong pool.** That,
plus panels that hide instead of unload (so everything opened stays resident),
plus a habit of fixing one paint producer at a time, is the "flaw in our design
and processes."

## The three-layer architecture

Industry practice for long-lived Chromium embedders (and browsers themselves)
layers three independent defenses. We have touched layer 1 repeatedly and skipped
2 and 3. Gold-standard is to invest in all three, weighted by measured leverage.

### Layer 1: produce less (paint and animation discipline)

Reduce the rate of reclaimable allocation. We have done a lot here already
(compositor-promote animations, `content-visibility`, remove the low-end raster
tint, fix listener leaks). The measurement above shows this layer has **reached
diminishing returns for this scenario**: pausing every animation did not change
the slope. Keep the discipline as a standard (animate only `transform` / `opacity`,
pause decorative animation when not foreground, avoid en-masse infinite
animations), but do not expect it to solve the multi-GB residency.

### Layer 2: bound residency (unload, do not just hide)

This is the browser "tab discarding" pattern (Chrome Memory Saver, Firefox unload
inactive tabs): a view that is not in front should release its resources, and
rebuild when shown again. Today every panel uses `classList.add('hidden')` and
stays fully resident (DOM, observers, timers, decoded images). With most panels
open, all of it is live at once.

Concrete moves, in rough order of leverage:

- Tear down heavy panels when closed (and optionally after a TTL while hidden):
  clear the panel's container, stop its timers, disconnect its observers, then
  rebuild on next open. Start with the heaviest by node count measured here:
  `doclib-modal` (4244), `cookbook-modal` (2978), `settings-modal` (2835).
- Virtualize the remaining long lists the way chat history already is (memory,
  email, doclib, tasks), so off-screen rows hold no DOM or tiles.
- A single shared lifecycle hook in the modal manager so every panel opts into
  teardown-on-close uniformly, rather than each panel reinventing it.

### Layer 3: reclaim (synthesize the missing pressure signal)

Because the OS signal never arrives, the app must generate it.

**Measured correction (2026-06-25):** the wrapper already wires the triggers
below, but it calls `Memory.simulatePressureNotification('critical')`, which on
this QtWebEngine build is a **no-op** — tested live, RSS 4861 to 4884 MB
(unchanged) after the call. That is why memory climbs unbounded despite the
existing "idle tile eviction": the triggers fire but the call reclaims nothing.
The call that actually works is `Memory.forciblyPurgeJavaScriptMemory` (page
target), measured reclaiming 5.2 GB and 3.7 GB in separate calls. The `gc()`
calls already in the wrapper only collect the 43 MB JS/Oilpan pool, not the
multi-GB renderer cache. So the fix is to replace the no-op call with the
forcible purge, gated, at the triggers that already exist.

Trigger it where a brief stall is invisible (a forcible purge does cause the
~1 second stutter that is still present, so timing discipline is mandatory):

- on window blur / deactivate, and on minimize (tie into the
  `setLifecycleState(Frozen)` work already drafted in the wrapper plans),
- after a panel is closed / torn down,
- on an idle timer when no streaming or input is in flight,
- on an RSS threshold (read renderer VmRSS; purge when it crosses a ceiling).

**Central design constraint (the ~1s stutter is still present).** A heavy
renderer purge (`forciblyPurgeJavaScriptMemory`) causes a roughly 1 second
stutter. This was never fixed (Session 4 fixed a different stutter). So the rule
is mandatory: never purge while the user is interacting. Fire only when a stall
is invisible (window blur, minimize, deep idle, post-panel-close), and only when
it is worth it (renderer RSS above a ceiling), and rate-limited so it cannot
repeat back to back. Run the purge off the main thread (in the CDP executor) so
the socket I/O does not add to the stall. This timing discipline is the
load-bearing detail of the reclaim layer, not a footnote.

## 2026-06-25 follow-up: idle climb is real, two producers, reclaim made periodic

After the first reclaim fix landed, the app still climbed while idle with panels
open and eventually filled all RAM. Two findings:

1. **The reclaim was single-shot.** The mouse-idle trigger fired once when the
   mouse stopped and only re-armed on the next mouse move. A user who walked away
   got exactly one purge, then unbounded climb. Fixed: a repeating sustained-idle
   timer (every 4s, purge if no input for 3s), keyboard-aware so typing defers it.
   `_purge_renderer` keeps the RSS-ceiling + rate-limit, so an idle-but-present
   user sees a reclaim only every few minutes. This bounds memory regardless of
   the producer.

2. **Two producers, measured (ev() parsing corrected this time).** With ~10
   panels open and zero input, RSS climbed ~5 MB/s. Cancelling all 24 running CSS
   animations (verified 0 running) dropped it to ~3.1 MB/s. So:
   - ~1.7 MB/s from perpetual CSS animations. The dominant one is
     `memory-synapse-sweep`, a decorative shimmer on every `#memory-list
     .memory-item::after` (~21 instances). Already paused when the Brain panel is
     hidden; still runs while it is open. Layer 1 target and an aesthetic decision.
   - ~3.1 MB/s from a non-animation continuous repaint that also saturated the
     renderer main thread (CDP went unresponsive under it: this is the CPU cost
     too). Backdrop-filter ruled out (0 visible). **Later identified** by a
     read-only rAF caller-stack capture as a **leaked whirlpool spinner**
     (`Spinner._drawWhirlpool`) looping forever on a detached canvas (the
     unbounded `!_wpWasConnected` grace). Fixed in #107 (a shared visibility guard
     for all three spinner loops). A further ~1.7 MB/s producer was then found
     when Tasks was open: the `#tasks-clock` 1/sec repaint re-rastering the whole
     draggable Tasks-modal layer — fixed in #110 by isolating the clock to its own
     layer. Lesson: name the producer (rAF/mutation capture, `tooling/mem-probe.py`)
     before fixing; do not guess.

Also fixed in this pass: the minimize page-freeze (`setLifecycleState(Frozen)`)
left the UI unresponsive after restore (Qt: a visible page must stay Active; a
non-Active page can lose input). Removed; minimize now keeps the page Active and
reclaims via the gated purge instead (#109).

Net: memory is now **bounded** by the periodic reclaim. Reducing the two
producers (Layer 1) and unloading hidden panels (Layer 2) lowers the steady-state
footprint and the CPU, and cuts how often the purge must fire.

## Sequencing and the single highest-leverage first step

1. **First (highest leverage, smallest change): fix the reclaim call.** The
   triggers already exist in the wrapper (periodic, mouse-idle, focus-loss,
   minimize); they call the no-op `simulatePressureNotification`. Replace it with
   `Memory.forciblyPurgeJavaScriptMemory`, gated by an RSS ceiling + rate limit
   and fired only off the interaction path. The measurement proves this alone
   recovers most of the footprint (5.2 GB in one call). This is the change that
   turns "climbs forever" into "bounded." (Issue #106.)
2. **Second: residency.** Add teardown-on-close to the modal manager and apply it
   to the three heaviest panels, then virtualize the long lists. This lowers the
   ceiling the reclaim has to fight and reduces how often it must fire.
3. **Third: keep layer-1 discipline** as a review standard, not a project.
4. **Parallel: instrument.** Log renderer VmRSS and DOM counters periodically so
   regressions show up as a slope, and keep the CDP slope-test method used here
   as the standard way to prove a producer before fixing it.

Each of these is upstream-candidate (the platform gap affects all Odysseus
users), and each should be its own issue and branch from `upstream-mirror`.

## Process change (the "and processes" part)

- **Measure before fixing.** Attach to CDP (port 9222 is already exposed), read
  the slope, and prove the producer with a pause / disable test before writing a
  fix. Several past fixes optimized producers that the slope test here shows were
  not the dominant cost.
- **Treat reclaim as policy, not per-feature.** One standing memory-pressure
  policy in the wrapper plus one residency policy in the modal manager, instead
  of per-widget paint tweaks.
- **Budget, then features.** Track a renderer RSS ceiling as a product
  requirement so the app remains usable on modest hardware.

## Open decisions (need the user)

- **Aesthetics vs reclaim aggressiveness.** Tearing down hidden panels and
  pausing decorative animation when not foreground trades some visual continuity
  (rebuild flicker on reopen) for memory. How aggressive to be is a product call.
- **Discard timing.** Teardown immediately on close, or only after a hidden TTL,
  or only under RSS pressure.
- **Scope now.** Whether to implement step 1 (reclaim) immediately as the urgent
  relief, and stage 2 and 3 as separate tracked work.

## Sources

- QtWebEngine does not release renderer memory / no pressure handling:
  https://forum.qt.io/topic/107455/qtwebengine-uses-up-all-memory-and-will-not-give-it-back ,
  https://forum.qt.io/topic/144953/freeing-all-memory-of-the-qwebengine-and-qt-quick ,
  https://forum.qt.io/topic/121122/memory-is-not-released-after-qwebengineview-was-deleted ,
  https://wiki.qt.io/QtWebEngine/Rendering
- Chromium memory pressure mechanism (the signal QtWebEngine does not drive):
  https://chromium.googlesource.com/chromium/src/+/HEAD/base/memory/memory_pressure_listener.h ,
  https://www.chromium.org/developers/memory-usage-backgrounder/
- CDP reclaim trigger (`Memory.simulatePressureNotification`,
  `forciblyPurgeJavaScriptMemory`):
  https://chromedevtools.github.io/devtools-protocol/tot/Memory/ ,
  https://codereview.chromium.org/1375633006
- Background / inactive view discarding as the residency pattern:
  https://support.mozilla.org/en-US/kb/unload-inactive-tabs-save-system-memory ,
  https://www.electronjs.org/docs/latest/tutorial/performance
- Caveat: GC and OS reclaim are not instant; measure slope over time, not a single
  reading: https://www.chromium.org/developers/memory-usage-backgrounder/
