# Low-Resource Profile: Design (Adaptive Loading for Odysseus)

**Status:** design (staged) · drives #116 · related: #117 (quiescence), `idle-reclaim-threshold-research.md`
**Date:** 2026-06-26

---

## Problem

On resource-limited setups Odysseus is more prone to stutter, from three distinct mechanisms:

1. **Software rendering** (no/weak GPU -> llvmpipe): every paint is CPU-rasterized. Scrolling,
   token streaming, and animations all cost far more; there is a floor we can't reach app-side.
2. **The forcible purge is slower** on a weak CPU (the ~1s freeze stretches to 2-3s+).
3. **The 60 s idle gate trades stutter for higher memory peaks**, fine when RAM is abundant, but
   on a **low-RAM** machine the higher peak can push the *whole system* into swap (everything
   stutters) or OOM-kill, which is worse than an app hitch.

The right behaviour is **hardware-dependent**: a capable box should minimise stutter (let memory
use the headroom, full effects); a constrained box should reclaim sooner and reduce effects,
*accepting* an occasional hitch because system swap/OOM is the worse failure.

## This is a standard pattern, not a guess: Adaptive Loading

"Detect device capability and serve a reduced experience to constrained devices" is the
**Adaptive Loading** pattern (Addy Osmani / Chrome team): in production at Facebook, eBay,
Tinder. Its canonical recommendations include, almost verbatim, *"throttling the frame-rate of
animations on low-end devices"* and *"avoiding computationally heavy operations on low-end
devices."* The capability signal is the **W3C Device Memory API** (`navigator.deviceMemory`),
designed to let apps *"serve a 'lite' version to low-memory devices."* Chromium's own
`IsLowEndDevice()` / low-end-device-mode is the engine-internal precedent for the same idea.

Sources:
- Adaptive Loading: <https://addyosmani.com/blog/adaptive-loading/>
- Device Memory API (W3C): <https://www.w3.org/TR/device-memory/> · MDN
  <https://developer.mozilla.org/en-US/docs/Web/API/Navigator/deviceMemory> · Chrome
  <https://developer.chrome.com/blog/device-memory>
- `prefers-reduced-motion` (effects reduction), already honoured in our CSS/JS.

## Detection (our refinement: a better signal than the web default)

`navigator.deviceMemory` is deliberately **coarse** (rounded to a power of two, quantised for
privacy: a known fingerprinting vector). Our reclaim levers live **host-side** (`qt_wrapper.py`),
where we can read a more accurate signal directly:

- **Total RAM:** `/proc/meminfo` `MemTotal` (host); exact, not bucketed.
- **Software rendering:** the GL renderer string / absence of a real DRM render node (the
  `llvmpipe` check we already proved out for the GPU incident).
- **Renderer-side (for effects):** `navigator.deviceMemory` + `prefers-reduced-motion`.

### Cross-platform: Rung-1's reclaim profile is Linux-specific *by necessity*

`/proc/meminfo` and `/dev/dri` are Linux-only, but the deeper reason Rung-1 doesn't simply "port"
is **the reclaim mechanisms differ per platform, and Rung-1 tunes the Linux one**:

- **Linux** (`qt_wrapper.py`): Chromium provides **no** memory-pressure evaluator
  (`CreateDefaultSystemEvaluator` -> `nullptr` on Linux; `simulatePressureNotification` is a no-op,
  verified). So Linux reclaims with the **blocking `forciblyPurgeJavaScriptMemory`**, which *must*
  be idle-gated, and Rung-1 adapts that gating (idle threshold + RSS ceiling) to device capability.
- **macOS / Windows** (`mac_wrapper.py` / `windows_wrapper.py`): Chromium **does** create a pressure
  evaluator (`#if IS_APPLE / IS_WIN`), so these wrappers reclaim via periodic
  **`simulatePressureNotification {critical}`** -> graceful, native, *non-blocking* eviction, the
  lazy reclaim Linux can't have. They have **no idle threshold / RSS ceiling** to tune, and they do
  **not** have the blocking-purge stutter Rung-1 exists to manage.

**Conclusion: Rung-1's reclaim profile is Linux-only on purpose: there is nothing for it to drive
on mac/Windows, and the problem it solves (a disruptive blocking purge) does not exist there.** A
mechanical "port the two readers" would be **dead code**. The `_classify_resources` mapping is still
reusable, but only once there is a *cross-platform consumer* (the renderer-side **reduced-effects**
mode (`prefers-reduced-motion` + a `low-power` class), which is platform-agnostic and the natural
place to apply `deviceMemory`/RAM detection on all three).

**Open question (needs on-device verification):** the research notes pressure handling is "hit and
miss on Windows, terrible/late on macOS." So mac/Windows reclaim *should* work but is **unverified by
us** (no mac/Windows hardware). If it proves inadequate on a real machine, those wrappers would need
the Linux blocking-purge approach *and then* Rung-1, but that's a per-platform investigation, not a
port. Until then, mac/Windows are correct as-is on their native pressure path.

Threshold for "low-resource" (defensible, not arbitrary): align with `IsLowEndDevice()`'s history
(<=512 MB originally, relaxed toward <=1 GB) and `deviceMemory` buckets; treat **<= ~2 GB total RAM
or software rendering** as the constrained profile. Exact cutoff is an app judgment; the *pattern*
and *signals* are standard.

## Detection fidelity: a ladder, not a single number

A static RAM threshold is the **entry rung**, not the last word. The known failure mode (from the
games world, where this is most mature) is that a fixed heuristic **mis-detects**; e.g. it can
flag newer-than-the-heuristic hardware as "low" or miss a fast-CPU/low-RAM box. So treat detection
as a ladder of increasing fidelity, and always keep the user override above all of it.

| Rung | Signal | Fidelity | Cost | Prior art |
|---|---|---|---|---|
| **0. Override** | explicit `ODYSSEUS_*` env vars | exact (user knows) | none | config-precedence best practice |
| **1. Static threshold** (ship this) | `/proc/meminfo` MemTotal + software-render check, at startup | good 80/20 | trivial | **Android `isLowRamDevice()`** ([docs](https://learn.microsoft.com/en-us/dotnet/api/android.app.activitymanager.islowramdevice)); **Chromium `IsLowEndDevice()`**; **`react-adaptive-hooks` `useMemoryStatus`** ([GoogleChromeLabs](https://github.com/GoogleChromeLabs/react-adaptive-hooks)) |
| **2. Runtime PSI downgrade** (natural next rung) | the existing `/proc/pressure/memory` monitor demotes the profile when *real* pressure appears | adapts to actual conditions, not a guess | low; **we already have the monitor** | OS memory-pressure adaptation (Android low-memory callbacks; Chrome Memory Saver) |
| **3. Benchmark / hw database** | a quick CPU/GPU micro-benchmark -> performance index, or match against a config database | highest | high (complexity, a benchmark hitch at startup) | **Unreal Engine auto-detect** ([Tom Looman](https://tomlooman.com/unreal-engine-optimal-graphics-settings/)); **NVIDIA App Game Optimizer** |

**Our plan:** ship **Rung 1** (matches Android/Chrome/react-adaptive-hooks, the standard 80/20)
with **Rung 0** override always winning. **Rung 2** is the natural follow-up and cheap for us
because the PSI monitor already exists; it turns "guess from a number at startup" into "react to
real pressure," which is strictly better. **Rung 3** (benchmark/database) is the games-grade
ceiling; only worth it if Rungs 1-2 prove insufficient on real hardware. Honest caveat: none of
this is validated against real low-end devices yet; the threshold is reasoned from the cited
standards, not measured, so Rung-0 override and Rung-2 runtime correction are what keep a
mis-detect from being painful.

## Response: the levers (most already exist)

| Lever | Capable default | Low-resource profile |
|---|---|---|
| Idle reclaim threshold (`ODYSSEUS_IDLE_RECLAIM_S`) | 60 s (Idle Detection API standard) | **lower** (~15-20 s); reclaim sooner |
| RSS purge ceiling (`ODYSSEUS_PURGE_CEILING_MB`) | ~1.2 GB | **lower** (e.g. 600-800 MB, >=512 floor) |
| Decorative effects | full | **reduced** (extend `html.app-blurred` quiescence to an `html.low-power` class; honour `prefers-reduced-motion`) |

Both reclaim knobs are **already env-tunable today** (a low-RAM user can set them manually). What's
missing for #116 is the **auto-detection** that selects the profile, so the app adapts instead of
the user guessing.

## Plan (#116)

1. At startup, compute a capability tier from `/proc/meminfo` + the software-render check.
2. If constrained: apply the low-resource defaults to the two reclaim knobs (unless the user has
   set the env vars explicitly: explicit override wins), and add `html.low-power` so CSS can pause
   non-essential animations (the #117 primitive generalised).
3. Log the chosen tier once (so it's diagnosable), e.g. `[PROFILE] low-resource (RAM 1.8 GB,
   software render): idle=20s ceiling=700MB reduced-effects=on`.
4. Do **not** flip `--enable-low-end-device-mode`, we want the adaptive behaviour *without* its
   16-bit-color/lighter-rectangle regression (already rejected; see qt_wrapper flags comment).

Net: a textbook Adaptive Loading implementation, host-side, with a more accurate signal than the
web default and our own levers; citable, not invented.
