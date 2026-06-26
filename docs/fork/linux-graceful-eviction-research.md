# Adding Graceful (Lazy) Memory-Pressure Eviction to Linux — Research & Plan

**Goal:** give QtWebEngine on Linux the **non-blocking, incremental** cache eviction that macOS /
Windows already have, so Odysseus no longer needs the blocking `forciblyPurgeJavaScriptMemory`
(the ~1 s stutter). The intended outcome is an **upstream PR** ("build it and they're more likely
to take it"). Related: `idle-reclaim-threshold-research.md`, #116. Date: 2026-06-26.

---

## 1. The gap (recap, source-confirmed)

Chromium reclaims renderer caches gracefully when its **`MemoryPressureMonitor`** receives an OS
pressure signal: it dispatches `MemoryPressureLevel` (moderate/critical) to every process's
`MemoryPressureListener`, and Blink/V8/Skia evict caches incrementally — **no blocking GC, no
stutter.** The OS signal comes from a platform **`SystemMemoryPressureEvaluator`**.

The Linux gap is one branch:

```cpp
// components/memory_pressure/system_memory_pressure_evaluator.cc
std::unique_ptr<SystemMemoryPressureEvaluator>
SystemMemoryPressureEvaluator::CreateDefaultSystemEvaluator(MultiSourceMemoryPressureMonitor* m) {
#if   BUILDFLAG(IS_FUCHSIA)  return …;
#elif BUILDFLAG(IS_APPLE)    return …;   // mac evaluator
#elif BUILDFLAG(IS_WIN)      return …;   // win evaluator
#else                        return nullptr;   // ← desktop Linux: NO evaluator
#endif
```

No evaluator ⇒ no pressure votes ⇒ no eviction. (ChromeOS/Chromecast have their own evaluators in
separate components; desktop Linux was simply never given one.) This also explains why
`Memory.simulatePressureNotification` is a measured no-op for us.

## 2. What an evaluator must do (small, well-defined interface)

A `SystemMemoryPressureEvaluator` subclass (ref: `system_memory_pressure_evaluator_win.cc`,
~200 LOC for the subclass):

- ctor takes a `MemoryPressureVoter`; `Start()` begins monitoring.
- watch the OS for pressure; on change, `voter_->SetVote(level, notify)` then `SendCurrentVote()`.
- Win uses OS notifications + a 2 s repeating timer while under pressure; thresholds scale with RAM
  (small: moderate 500 MB / critical 200 MB; ≥1.5 GB: moderate 1000 / critical 400).

**The Linux analog is the bulk of the code** and is genuinely small (~200–350 LOC).

## 3. The Linux signal — three options (recommend PSI)

| Signal | How | Pros | Cons |
|---|---|---|---|
| **PSI** `/proc/pressure/memory` *(recommended)* | register a trigger (write `some <stall_us> <window_us>`), `poll()` the fd for events | event-driven, kernel-grade, the modern standard (Linux ≥4.20), what ChromeOS uses | needs a sane stall threshold; host-PSI vs cgroup-PSI distinction |
| **systemd / cgroup** `memory.pressure` + `sd_event_add_memory_pressure(3)` | per-cgroup PSI via systemd | correct under containers/cgroup limits | systemd dependency; not all distros/sessions |
| **`/proc/meminfo` polling** (the 2015 starter, crrev 1250093006) | poll MemAvailable on a timer, RAM-scaled thresholds like Win | no kernel-version dep; mirrors Win/Mac exactly | polling (not event-driven); pre-PSI legacy |

Recommendation: **PSI**, with a `/proc/meminfo`-polling fallback for kernels without PSI — this
matches ChromeOS (the closest existing reference) and is the senior choice.

## 4. The TWO pieces (this is the part people miss)

Adding the evaluator is necessary but maybe not sufficient for **QtWebEngine specifically**:

1. **Evaluator** — add the Linux `SystemMemoryPressureEvaluator` (§2–3). Benefits *all*
   Chromium-on-Linux.
2. **Monitor instantiation** — *someone* must create the `MultiSourceMemoryPressureMonitor` in the
   **browser process**. Chrome does this in its browser main parts. **QtWebEngine may not** — and if
   it doesn't, the evaluator never runs. ⚠ **Unverified; first investigation step.** Our measured
   no-op of `simulatePressureNotification` is a hint that the dispatch may not be wired in
   QtWebEngine at all — pin this down before estimating the Qt side.

## 5. Contribution paths (and which to pick)

| Path | Lands in | Effort to land | Reaches Odysseus when | Notes |
|---|---|---|---|---|
| **A. QtWebEngine (Qt)** *(recommended for us)* | Qt Gerrit (`qtwebengine`) | medium | next Qt release (months) | Qt carries Chromium patches in `src/3rdparty/chromium`; can add evaluator **+** monitor instantiation together. Directly fixes Odysseus's runtime. |
| **B. Chromium** | Chromium Gerrit | high (CLA, OWNERS, chrome-memory@ design review) | only after QtWebEngine rebases onto that Chromium (≈1–2 yr) | Biggest impact (Chrome/Electron/CEF/Qt all benefit). Slow for *us*. |
| **C. Local patched Qt build / AppImage** | our distribution | low-med (build infra) | immediately, on our builds only | Unmaintainable long-term, but the way to **prototype + measure** before upstreaming. |

Strategy: **C to prototype and prove the win → A to land it where it helps Odysseus → optionally B**
for the ecosystem (citing the working Qt patch). Prior community interest exists — Igalia (the firm
behind much Linux Chromium/WebKit embedding) has discussed Linux embedded memory pressure on
chromium-dev.

## 6. Why is it `nullptr` today? (the risk to de-risk first)

Desktop Linux was *deliberately* left without an evaluator, and a reviewer **will** ask why we
think that's safe to change. Likely reasons / risks to address in the PR:

- **No single good threshold** across the huge variety of Linux configs (swap on/off, zram,
  cgroup limits, headless servers). Over-eager eviction would *hurt* (constant cache re-fill).
- **Host PSI vs the app's cgroup** — host pressure may not reflect the browser's own budget.
- **Double reclaim** — interacting with our own PSI monitor / the OS killer.

These are *design* questions, not blockers — but they're why this is a "research + measure +
justify," not a drive-by patch.

## 7. Effort estimate (honest)

| Task | Effort |
|---|---|
| Verify QtWebEngine creates the monitor (§4) | 0.5–1 day (read Qt browser main parts; instrument a build) |
| Linux PSI evaluator (adapt ChromeOS/Win) | ~200–350 LOC, **2–4 days** |
| Wire into `CreateDefaultSystemEvaluator` (+ monitor if missing) | hours |
| **Build QtWebEngine from source** (the real time sink) | env setup **1–3 days**; ~100 GB disk; **hours per rebuild** |
| Threshold tuning + measure on real low-RAM hardware | **3–7 days** (needs a constrained box) |
| Upstream review (Qt Gerrit; or Chromium) | **weeks–months** elapsed, design pushback likely |

**Net:** the *code* is small (~a week of focused work). The cost is **the build/test environment,
threshold validation on real hardware, and the review process** — realistically **~1–2 weeks to a
working prototype** (path C), **1–3 months** to land upstream (path A). One person can do it.

## 8. Phased plan

1. **Verify the monitor gap** in QtWebEngine (does it create `MultiSourceMemoryPressureMonitor`?).
   This decides whether the fix is "evaluator only" or "monitor + evaluator."
2. **Prototype (path C):** add a PSI evaluator (+ monitor if needed) to a local QtWebEngine build;
   confirm via CDP that `simulatePressureNotification` and real pressure now evict (RSS drops with
   **no** main-thread stall — the win we want). Measure on a real ≤4 GB box.
3. **Measure vs the blocking purge:** prove graceful eviction keeps RSS bounded without the ~1 s
   freeze; tune PSI thresholds; check no over-eviction (cache thrash).
4. **Upstream (path A):** submit to Qt with the measurements + the design answers from §6; keep the
   local patch until it ships. Consider the Chromium PR (path B) afterward, citing the Qt result.
5. On land: Odysseus drops the Linux blocking-purge + idle-gating (or keeps it as a fallback for
   pre-PSI kernels); Rung-1's reclaim-profile becomes unnecessary on Linux (it becomes like mac/win).

## 9. Open questions to resolve before coding
- Does QtWebEngine instantiate the memory-pressure monitor at all? (§4 — decides scope.)
- PSI host vs cgroup for a desktop app — which budget do we trust?
- Threshold defaults that don't thrash across swap/zram/cgroup configs (tie to Rung-1 RAM detection).

## Sources
- CDP no-op + `nullptr` proof: `idle-reclaim-threshold-research.md` (this fork).
- PSI: <https://docs.kernel.org/accounting/psi.html> · systemd `sd_event_add_memory_pressure(3)`.
- Evaluator reference: `components/memory_pressure/system_memory_pressure_evaluator_win.cc`
  (Chromium); the 2015 Linux starter crrev/1250093006; ChromeOS PSI evaluator.
- Community: chromium-dev "Memory pressure in an embedded linux environment" (Igalia).
