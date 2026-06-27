# Graduated PSI reclaim plan (issue #120)

Execution plan for the graduated PSI monitor in `qt_wrapper.py`. Related memory work:
`docs/fork/memory-management-architecture.md` (layer 3 reclaim, #106) and
`docs/fork/plans/memory-management-plan.md`.

**Issue #120. Branch `perf/qt-psi-graduated-reclaim` (stacks on
`perf/renderer-memory-reclaim`, the #106 branch — not on `feat/qt-native-linux-app`).
#106 supplies `_purge_renderer`, the RSS-ceiling env knobs, `_renderer_rss_kb`, and the
PSI monitor this reworks; #106 is a *sibling* of `feat/qt-native-linux-app`, not chained
onto it, so the upstream-PR ordering must carry #14 → #106 → #120. Implemented; cherry-
picked to develop (`9e6ca024`).**

The wrapper's PSI monitor (`qt_wrapper.py:455`) today is a daemon thread that reads only
`some` avg10 and, above a flat 5%, sets a module flag (`_request_async_gc`) drained on the
Qt main thread by a 250 ms `QTimer` (`:780-791`).

Two outcomes, equally weighted:
1. The wrapper reclaims **proportionally** to real pressure (graduated NONE/MODERATE/
   CRITICAL from `some`+`full`, matching the `chromium-linux-mempressure` harness).
2. It emits structured telemetry that **field-validates the threshold table**
   (`some 10/40`, `full 5`) used by that separate PSI evaluator. The evaluator is a
   Qt/Chromium-upstream contribution which eventually supersedes this monitor; both share the
   same validated logic (its `harness/psi_logic` is the executable reference). This is the
   production data the desk phase could not get, so it directly de-risks the eventual build.

## Decisions (resolved)

- **CRITICAL keeps the RSS-ceiling gate.** The CRITICAL action reuses `_purge_renderer`
  as-is, which is gated by `_PURGE_RSS_CEILING_KB` and the `_PURGE_MIN_INTERVAL_S` rate
  limit. We do **not** bypass the ceiling on `full`-stall. Rationale: the renderer purge only
  helps when the renderer is the consumer, the ceiling already encodes "worth the ~1 s
  stutter," and bypassing it risks paying the stutter when the renderer is not the problem.
  If telemetry later shows genuine system pressure with the renderer below ceiling, revisit
  then with data, not speculatively.

## The boundary problem this plan resolves

Three facts about the live code force the design:

1. **The monitor is a daemon thread with no Qt event loop.** It must not touch Qt/CDP. It
   can only read `/proc` and hand data to the main thread — exactly what `_request_async_gc`
   already does.
2. **The telemetry line needs main-thread-only data.** `rss_mb` comes from
   `_renderer_rss_kb()` (a window method, `:831`), and the action is dispatched on the main
   thread. So the `[PSI]` line must be emitted by the drain timer, not the monitor thread.
3. **The `action` outcome is two-phase.** `_purge_renderer` (`:845`) decides ceiling/
   rate-limit/submit synchronously but runs the CDP purge later in `_do()` on
   `_cdp_executor`. So the transition line logs the *decision* (`purge_submitted` /
   `purge_skipped_ceiling` / `purge_rate_limited` / `async_gc` / `none`); the *realized*
   result is the existing `[MEM] forcible purge (psi-critical): ok … delta=…` line, tied
   back by the `reason` string. Do not contort `_purge_renderer` into a deferred return.

## Architecture: monitor computes, drain timer acts (mirrors `_gc_request_pending`)

The daemon monitor thread owns the FSM (prev_level + cooldown/hysteresis timing) and does no
Qt work. On a transition worth emitting, it writes one record into a module-level single-cell
list (GIL-atomic assignment, same rationale as `_gc_request_pending`, `:416-419`):

```python
# module level, beside _gc_request_pending
_psi_event_pending: list[dict | None] = [None]
# record: {level, some, full, mem_avail_mb, swap_mb, requested}
# requested in {'none','async_gc','critical'}
```

The existing 250 ms drain (`_drain_gc_requests`, `:780`) gains a PSI stanza: read+clear the
cell, add `rss_mb` via `_renderer_rss_kb()`, dispatch the requested action, and emit the
single `[PSI]` line with the now-known synchronous `action`. All Qt/CDP stays on the main
thread.

## Code changes (all in `qt_wrapper.py`)

1. **Env-tunable thresholds** beside `_PURGE_RSS_CEILING_KB` / `_IDLE_RECLAIM_AFTER_S`
   (`:383-408`), same `try/except`-float + floor pattern:
   - `ODYSSEUS_PSI_MODERATE` (default `10.0`, `some_avg10`)
   - `ODYSSEUS_PSI_CRITICAL` (default `40.0`, `some_avg10`)
   - `ODYSSEUS_PSI_FULL_CRITICAL` (default `5.0`, `full_avg10`)
   Add their keys to the `_profile_overridden` set (`:411`) and log them in the `[PROFILE]`
   line (`:412-414`) so every data run is self-describing.

2. **Pure, testable decision functions** (module level, so the tests reach them without a
   running Qt app — the current `_loop` inlines the decision and is untestable):
   - `_psi_level(some, full, *, moderate, critical, full_critical) -> str` — direct
     transliteration of the harness `CalculatePressureLevel`: `CRITICAL` if
     `some >= critical or full >= full_critical`; `MODERATE` if `some >= moderate`; else
     `NONE`.
   - `_psi_should_emit(prev_level, level, now, last_emit, *, cooldown) -> bool` — the
     harness `CheckMemoryPressure` discipline, reproduced with its **three distinct arms**
     (code-study.md:29-36), not a uniform cooldown:
     - **NONE:** emit only on the down-transition from a pressure level (not while idle).
     - **MODERATE:** emit on entry, then re-emit only every `cooldown` while sustained.
     - **CRITICAL:** **emit every poll** (always notify). Acting is still throttled by
       `_purge_renderer`'s 15 s rate-limit + ceiling, and denser telemetry during a rare
       CRITICAL episode is exactly when the validation data is most wanted.
     One gate drives **both** act and emit — the log is a faithful record of *when the
     harness policy would notify*, which is the property being field-validated. The ~60 s
     heartbeat (step 7) is the lone emit-without-act path. Keeps the discipline out of the
     I/O loop and under test.

3. **Helpers for the system-correlation fields** (module level, single `/proc` read each):
   - `_read_mem_available_mb() -> int | None` from `/proc/meminfo` `MemAvailable`.
   - `_read_swap_used_mb() -> int | None` from `/proc/meminfo` `SwapTotal - SwapFree`
     (this is the `swap_mb` in the telemetry).

4. **Rework `_start_psi_monitor` loop** (`:474-495`): read both `some` and `full` avg10
   (parse the `full` line too — present for memory PSI on all supported kernels); compute
   `level = _psi_level(...)`; gate with `_psi_should_emit(...)` against `prev_level` /
   `last_emit` / cooldown; on emit, read `mem_avail_mb` + `swap_mb`, set `requested`
   (`MODERATE -> 'async_gc'`, `CRITICAL -> 'critical'`, down-to-NONE -> `'none'`), write the
   record to `_psi_event_pending`, update `prev_level`/`last_emit`. No Qt calls in the loop.
   Keep the `os.path.exists(_PSI_PATH)` kernel guard (`:471`).

5. **Extend the drain timer** (`_drain_gc_requests`, `:780-791`): after the GC stanza, add
   the PSI stanza — pop `_psi_event_pending`; if present, compute `rss_mb`; dispatch:
   - `async_gc` -> the existing JS GC (`page.runJavaScript("…gc({type:'major'…})")`, already
     here) and `action='async_gc'`;
   - `critical` -> `status = self._purge_renderer('psi-critical')` and map the status to
     `action` (`purge_submitted` / `purge_skipped_ceiling` / `purge_rate_limited`);
   - `none` -> `action='none'`.
   Then emit the one `[PSI]` line. (The new stanza calls `self._purge_renderer` /
   `self._renderer_rss_kb`; `_drain_gc_requests` currently closes over `page` — it is nested
   where `self` is in scope, `self._gc_drain_timer` is assigned just after it, but confirm at
   implementation.)

6. **`_purge_renderer` returns a synchronous decision status** (`:845-875`): the ceiling
   skip (`:859`) returns `'skipped_ceiling'`, the rate-limit skip (`:862`) returns
   `'rate_limited'`, and the submit path (`:875`) returns `'submitted'`. The `ok/FAILED`
   realized outcome stays in `_do()`'s existing `[MEM] forcible purge` line. Existing callers
   (`focus-loss`, `minimized`, `post-interaction-idle`, `sustained-idle`) ignore the return,
   so this is additive.

7. **Heartbeat (~60 s):** the loop emits one `[PSI] level=NONE … action=none` line on a
   slow cadence even without a transition (via the same record path), so the trajectory is
   sampled without log spam.

## Telemetry — the chromium-validation payload

One greppable line per transition (and per heartbeat), emitted by the drain timer:

```
[PSI] level=CRITICAL some=45.2 full=6.1 mem_avail_mb=410 rss_mb=1850 swap_mb=900 action=purge_submitted
```

- `mem_avail_mb` (host `MemAvailable`) is correctness-critical: PSI is a *system* signal;
  without it the data cannot separate genuine low-memory from spurious fires.
- `swap_mb` = `SwapTotal - SwapFree`. The reclaim path PSI rides; needed to read the ramp.
- `action` is the synchronous *decision*; the realized purge result is the paired
  `[MEM] forcible purge (psi-critical)` line, joined by the `psi-critical` reason.

**Feedback loop:** `grep '\[PSI\]' logs/wrapper_system.log` across real sessions; analyze
fire-frequency, false-trip rate (a level firing while `mem_avail_mb` is high), and
`MemAvailable` correlation; confirm or nudge `some 10/40, full 5`, recording back in the
chromium project's `pre-build-calibration.md` and open-questions threshold item.

### Limits of this data (state plainly; do not oversell)

- Single-hardware **trigger sanity check**, not a fleet study; one box, one workload, an
  actuator (Python GC / CDP purge) that differs from Chromium's in-engine cc/V8/Skia
  eviction. Does not answer the maintainer's diverse-hardware A/B objection.
- Validates the avg10 **percentage** threshold form; only partial transfer if the evaluator
  moves to stall-time `poll(POLLPRI)` triggers (design.md Axis 2).
- Scope-limited on purpose: no observe-only mode, CSV pipeline, or per-poll ramp sampling
  here — that observational job is `harness/sample_workload.sh`'s; the ramp shape is already
  characterized by the disk-swap probe. This monitor measures whether *shipped behavior* is
  sane.

## Tests (`tests/test_psi_monitor.py`)

The decision functions are now importable, so these are real unit tests, not source greps:

- `_psi_level` boundaries mirroring the harness: `some 9 -> NONE`, `10 -> MODERATE`,
  `39 -> MODERATE`, `40 -> CRITICAL`; `full 4.9 -> (by some)`, `full 5 -> CRITICAL`.
- `_psi_should_emit`, all three arms: sustained MODERATE re-emits only past cooldown;
  sustained **CRITICAL emits every poll** (always notify); NONE emits only on the
  down-transition, never while idle (no flap).
- Env-override parsing: defaults 10/40/5; overrides applied; floor enforced.
- `_read_mem_available_mb` / `_read_swap_used_mb` parse a sample `/proc/meminfo` fixture
  (and return `None` on malformation).
- A source-audit check (consistent with `tests/test_qt_cdp_listener_audit.py`) that the
  drain timer carries the PSI stanza and that `_purge_renderer` has a `return` on each gate.

## Acceptance & verification

- Classifies NONE/MODERATE/CRITICAL from `some`+`full`; MODERATE -> async GC, CRITICAL ->
  gated `_purge_renderer`; thresholds env-tunable; no flapping; degrades on kernels < 4.20
  (no PSI file -> monitor returns, app unaffected).
- Live: `stress-ng --vm 2 --vm-bytes 90%`; confirm graduated actions fire, the `[PSI]` line
  captures the transition with sane `mem_avail_mb`/`rss_mb`/`action`, and the paired
  `[MEM] forcible purge (psi-critical)` line shows the realized delta on CRITICAL. Confirm a
  normal session yields a clean NONE heartbeat trajectory and no spurious CRITICAL.
- `pytest tests/test_psi_monitor.py -v` green; cherry-picked to develop (`-x`); branch
  `perf/qt-psi-graduated-reclaim` retained for the #14 PR.

## Safety / rollback

Confined to the daemon-thread monitor (already `try/except`-wrapped) plus one added stanza
in the existing drain timer and a synchronous return added to `_purge_renderer`. Mis-tuned
thresholds are env-overridable or revertible per-function. No behavior change to the
existing RSS-ceiling/idle purge paths (#106) beyond adding `psi-critical` as a caller and a
status return the old callers ignore.
