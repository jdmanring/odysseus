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

## 1b. Prior art — YES, and it reframes everything (Gerrit-confirmed 2026-06-26)

**There was a near-complete Chromium CL, and it was abandoned for a structural reason — read this
before writing any code.**

**Chromium CL [7594942](https://chromium-review.googlesource.com/c/chromium/src/+/7594942)** — *"Add
PSI-based memory pressure monitoring for Linux"* by **Helmut Januschka** (external contributor),
created 2026-02-23, **abandoned by the author 2026-04-09** after 5 patch sets. It **passed CQ** and
implements *exactly* our design:
`components/memory_pressure/psi_memory_pressure_evaluator_linux.{cc,h}` +
`pressure_stall_info_linux.{cc,h}` + unittests + `chrome/browser/chrome_browser_main_linux.cc`
wiring + a `chrome_features` flag + histograms.

**Why it was abandoned (the critical part — from the Chromium memory team in review):**
- Code quality was fine — Benoit Lize: *"the PSI parsing code looks correct, quite close to the one
  on CrOS."*
- **Google already wants Linux PSI** — Patrick Monette: *"Using Linux PSI for memory pressure
  monitoring is actually something that's been on our radar already."*
- **They are mid-rewrite of the whole memory-pressure architecture** (MemoryPressureListener →
  MemoryConsumer), so a new evaluator on the *old* architecture would be discarded. Design doc:
  <https://docs.google.com/document/d/1HT-ii0_gVPjV12NoYlnWbXfTWL4szqWDGnP63ysvRwQ>.
- **The hard part is tuning, not code** — Francois Doray: *"the main challenge is to tune the signal
  to maximize speed and stability, which likely requires field experiments"* (A/B) — which an
  external contributor cannot run.

**Strategic implications (this changes the plan in §5/§7/§8):**
1. **Do NOT attempt a from-scratch upstream Chromium PR** — Helmut had a CQ-passing CL *and* memory-
   team engagement and still couldn't land it, for reasons (architecture revamp + Google-only field
   experiments) that **we cannot overcome either**. We'd hit the same wall.
2. **For Odysseus, his code is a ready-made patch.** The evaluator + PSI parser are BSD-licensed
   Chromium code; we can **adapt CL 7594942 as a QtWebEngine patch** (path C: local patched Qt
   build) to get lazy eviction *now*, independent of Google's revamp — crediting Helmut.
3. **Upstream lands when Google's MemoryConsumer revamp does** — track that design doc + Patrick
   Monette's work, rather than push our own. A Qt-side patch (path A) is the only "contribute it"
   avenue worth pursuing, and even that competes with the in-flight rewrite.

Downstream reference implementations also exist (ChromeOS PSI monitor — Lize even links the CrOS
code; Chromecast; Endless OS), but **CL 7594942 is the best starting point** — it's the CrOS design
already ported to the exact `components/memory_pressure` desktop-Linux structure.

So the honest answer to "isn't someone already doing this?": **a complete attempt exists, abandoned
not because it's wrong but because Google is rebuilding the subsystem and gates the tuning behind
internal experiments.** Our realistic play is a **local/Qt patch reviving Helmut's code**, not an
upstream Chromium PR.

**Downstream implementations exist — adapt, don't invent:**
- **ChromeOS** — the canonical PSI `MemoryPressureMonitor` (the reference to port).
- **Chromecast** — maintains its own under `chromecast/`.
- **Endless OS** — *"a custom implementation based on ChromiumOS's MemoryPressureMonitor."* Most
  relevant: a **desktop-Linux distro shipping Chromium** — almost exactly our case. Primary
  reference to study (GPL/BSD Chromium licensing applies — check before lifting code).
- The 2015 starter CL `crrev/1250093006` (ChromeCast-context polling evaluator).

**Implication:** this lowers the build effort (port a known design, don't design one) **and**
strengthens the contribution case (a wanted, unowned gap with proven downstream precedent).

**Before writing code, still confirm nothing is mid-flight** on the live trackers (web search can't
see these well): Chromium issue tracker (`issues.chromium.org`, search "Linux memory pressure" /
"PSI evaluator"), Chromium Gerrit (`chromium-review.googlesource.com`), Qt (`bugreports.qt.io`,
QtWebEngine), and consider pinging the chromium-dev thread / Igalia (they own the most embedded-Linux
Chromium expertise and have already flagged it).

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

## 4. The pieces — RESOLVED 2026-06-26: it's the evaluator *only* (source-confirmed)

The earlier worry was that QtWebEngine might not even create the monitor (then no evaluator would
run). **That is now settled by reading current Chromium source — the monitor IS created in
`content/`, which QtWebEngine compiles:**

```cpp
// content/browser/browser_main_loop.cc — CreateMemoryPressureMonitor()
#if BUILDFLAG(IS_APPLE) || BUILDFLAG(IS_WIN) || BUILDFLAG(IS_FUCHSIA) || \
    BUILDFLAG(IS_LINUX) || BUILDFLAG(IS_CHROMEOS) || BUILDFLAG(IS_ANDROID)
  monitor = std::make_unique<memory_pressure::MultiSourceMemoryPressureMonitor>();
#endif
```

`IS_LINUX` is in the guard, so QtWebEngine's browser process **does** instantiate the monitor, and
the monitor's `MaybeStartPlatformVoter()` calls
`SystemMemoryPressureEvaluator::CreateDefaultSystemEvaluator(this)` — which returns **`nullptr`** on
Linux (§1, re-verified verbatim from `system_memory_pressure_evaluator.cc`). So:

- ✅ The **monitor** is wired (content/, runs in QtWebEngine).
- ✅ The **response** machinery is wired: monitor → `MemoryPressureListener` fan-out → cc/V8/Skia
  graceful eviction already exists and runs.
- ❌ The **only** missing piece is the **evaluator** (the detector that calls
  `voter_->SetVote(level)`), because `CreateDefaultSystemEvaluator` returns nullptr.

**Consequence — the patch surface is ONE self-contained component, no `chrome/` changes.** The fix
lives entirely in `components/memory_pressure/` (which QtWebEngine compiles): add a Linux evaluator
and make `CreateDefaultSystemEvaluator` return it on Linux. Helmut's CL also edited
`chrome/browser/chrome_browser_main_linux.cc`, `about_flags.cc`, `flag_descriptions.h`, etc. — those
are **Chrome-UI flag plumbing we can drop**; QtWebEngine has no `chrome/` and can enable the
evaluator via a build flag or unconditionally. This removes the previously-feared "monitor
instantiation" piece and the `simulatePressureNotification` no-op is now fully explained: the
listener fan-out works, but with no evaluator there is nothing to translate a simulated pressure
call into a vote on Linux.

## 4b. Detection source — PSI in-process vs. reuse the desktop `LowMemoryMonitor` signal

The evaluator's *detection* half can be sourced two ways, and this is the only place the
"why aren't we using what Endless OS has?" question actually bites. Both fit the same ~200 LOC slot;
the **response** glue (vote → `MemoryPressureListener`) is identical either way and is the part only
a Chromium-side patch can provide.

| Detection source | What it is | Pros | Cons |
|---|---|---|---|
| **In-process PSI** (Helmut's CL, ChromeOS) | evaluator reads `/proc/pressure/memory` itself | **zero runtime deps** (matters on Arch, headless, containers); self-contained; CQ-passing code to start from | re-implements PSI parsing; we own the thresholds |
| **Desktop signal** (`org.freedesktop.LowMemoryMonitor` via Chromium `dbus::Bus` — **not** GIO/`GMemoryMonitor`, see §4b note) | evaluator subscribes to the existing D-Bus `LowMemoryWarning` signal | reuses a maintained daemon; the standard GNOME/Endless desktop signal; thresholds tuned by the daemon | **adds a runtime dependency** (daemon installed + running — not default on Arch); no signal at all if absent; GIO path doesn't work in QtWebEngine |

**Key facts established this session:**
- Endless OS `psi-monitor`, `systemd-oomd`, `nohang` all *detect* pressure but *respond by
  killing/pausing whole processes* — wrong granularity; we want Chromium to **shrink**, not be
  OOM-killed.
- `low-memory-monitor` / `GMemoryMonitor` provide the *detection signal* (`LowMemoryWarning`, levels
  0–255) but **delegate the response to each app**. Chromium **does not subscribe today**, and across
  **all 37 review messages on CL 7594942 the Chromium memory team never raised this path** — it was
  simply not considered there.
- Therefore **no external project removes the need for a Chromium patch** — the graceful-eviction
  response lives inside Chromium. The desktop signal only changes the detector's *source*.

### Nailed down 2026-06-26 — the "D-Bus from sandbox" worry was misframed; the real catch is the main loop

Two questions had to be settled before picking a source. Both now resolved from source/spec:

1. **Sandbox is a non-issue.** The pressure monitor + evaluator run in the **browser process**, which
   is the *privileged, unsandboxed* process (only renderers/GPU are sandboxed; they request resources
   via IPC). Chromium's browser process **already opens session-bus connections** today (secret
   service / GNOME-keyring / KWallet, xdg portals, proxy config). So there is **no sandbox barrier**
   to a D-Bus subscription from the evaluator — the original "can it reach the bus under the sandbox?"
   framing doesn't apply, because the code path isn't sandboxed.

2. **The real catch is GIO needs a GLib main loop QtWebEngine doesn't run.** `GMemoryMonitor` is
   GIO/GDBus, and GDBus signals are only dispatched when a **`GMainContext` is being iterated**
   (GLib main-loop docs, confirmed). Chromium's desktop-Linux GLib pump (`MessagePumpGlib`) exists
   for GTK — but **QtWebEngine replaces the browser-process UI pump with Qt's event loop**, so no
   `GMainContext` is iterated there. A `GMemoryMonitor` subscription would compile and then **silently
   never fire**. ⇒ **Do not use GIO/`GMemoryMonitor` in QtWebEngine.** If we want the desktop signal,
   subscribe to `org.freedesktop.LowMemoryMonitor.LowMemoryWarning` via **Chromium's own `dbus::Bus`**
   (`components/dbus`, a dedicated libdbus thread with its own watch/timeout integration — **no GLib
   dependency**), which is how Chromium already does keyring/bluez D-Bus.

**Decision this tips:** in-process PSI is the clean primary source — **zero runtime deps, no D-Bus, no
main-loop coupling**, and it's the CQ-passing code (Helmut's CL / ChromeOS) we'd start from. The
desktop-signal path is viable but only via `dbus::Bus` (never GIO), and it buys us a *maintained
threshold* at the cost of a runtime daemon dependency not present on Arch. **Recommendation: ship
in-process PSI; treat the `dbus::Bus` `LowMemoryMonitor` subscription as an optional Rung-2-style
enhancement (prefer the daemon's signal when present, else PSI) — not the foundation.** This settles
the source decision that gated the repo charter.

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
| ~~Verify QtWebEngine creates the monitor (§4)~~ | ✅ **DONE** — source-confirmed it does (content/, `IS_LINUX`); only the evaluator is missing, no `chrome/` work |
| Linux evaluator (adapt CL 7594942 / ChromeOS/Win; pick PSI vs `GMemoryMonitor` per §4b) | ~200–350 LOC, **2–4 days** |
| Wire into `CreateDefaultSystemEvaluator` (evaluator only — monitor already exists) | hours |
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
- ~~Does QtWebEngine instantiate the memory-pressure monitor at all?~~ ✅ **Resolved (§4): yes,
  in content/ for `IS_LINUX`. Only the evaluator is missing.**
- ~~Detection source (§4b): PSI vs `GMemoryMonitor` vs hybrid~~ ✅ **Resolved (§4b): in-process PSI
  is the primary source; the desktop `LowMemoryMonitor` signal, if added, goes via Chromium
  `dbus::Bus` (never GIO/`GMemoryMonitor`) as an optional enhancement.**
- ~~D-Bus from the QtWebEngine browser process under its sandbox~~ ✅ **Resolved (§4b): no sandbox
  barrier (evaluator runs in the unsandboxed browser process); the actual constraint is that GIO
  needs a GLib main loop QtWebEngine doesn't run, so use `dbus::Bus`, not `GMemoryMonitor`.**
- PSI host vs cgroup for a desktop app — which budget do we trust? *(still open — measurement)*
- Threshold defaults that don't thrash across swap/zram/cgroup configs (tie to Rung-1 RAM detection).
  *(still open — needs real low-RAM hardware)*

## Sources
- CDP no-op + `nullptr` proof: `idle-reclaim-threshold-research.md` (this fork).
- PSI: <https://docs.kernel.org/accounting/psi.html> · systemd `sd_event_add_memory_pressure(3)`.
- Evaluator reference: `components/memory_pressure/system_memory_pressure_evaluator_win.cc`
  (Chromium); the 2015 Linux starter crrev/1250093006; ChromeOS PSI evaluator.
- Community: chromium-dev "Memory pressure in an embedded linux environment" (Igalia).
- GLib main-loop / GDBus dispatch requires `GMainContext` iteration: <https://docs.gtk.org/glib/main-loop.html>.
- Chromium browser process is the privileged/unsandboxed process (renderers sandboxed, request via IPC):
  Chromium `docs/linux/sandboxing.md`; `components/dbus` (libdbus on a dedicated thread, no GLib).
