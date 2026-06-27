# Graduated PSI reclaim plan (issue #120)

Execution plan for the graduated PSI monitor in `qt_wrapper.py`. Related memory
work: `docs/fork/memory-management-architecture.md` (layer 3 reclaim, #106) and
`docs/fork/plans/memory-management-plan.md`.

**Issue #120. Branch `perf/qt-psi-graduated-reclaim` (stacks on
`feat/qt-native-linux-app`). Not started.**

Two outcomes, equally weighted:
1. The wrapper reclaims **proportionally** to real pressure (today it fires a
   single async GC on a naive `some > 5%` trigger).
2. It emits structured telemetry that **field-validates the threshold table**
   (`some 10/40`, `full 5`) used by the separate `chromium-linux-mempressure`
   PSI evaluator. That evaluator is a Qt/Chromium-upstream contribution which
   eventually supersedes this monitor; both share the same validated logic (its
   `harness/psi_logic` is the executable reference). This is the production data
   the desk phase could not get, so it directly de-risks the eventual build.

## Decisions (resolved)

- **CRITICAL keeps the RSS-ceiling gate.** The CRITICAL action reuses
  `_purge_renderer` as-is, which is gated by `_PURGE_RSS_CEILING_KB` and the
  `_PURGE_MIN_INTERVAL_S` rate limit. We do **not** bypass the ceiling on
  `full`-stall. Rationale: the renderer purge only helps when the renderer is the
  consumer, the ceiling already encodes "worth the ~1 s stutter," and bypassing it
  risks paying the stutter when the renderer is not the problem. If telemetry later
  shows genuine system pressure with the renderer below ceiling, revisit then with
  data, not speculatively.

## Code changes (all in `qt_wrapper.py`)

1. **Env-tunable thresholds** beside the existing knobs (`ODYSSEUS_PURGE_CEILING_MB`
   / `ODYSSEUS_IDLE_RECLAIM_S`):
   - `ODYSSEUS_PSI_MODERATE` (default `10.0`, `some_avg10`)
   - `ODYSSEUS_PSI_CRITICAL` (default `40.0`, `some_avg10`)
   - `ODYSSEUS_PSI_FULL_CRITICAL` (default `5.0`, `full_avg10`)
   Same `try/except`-float + floor pattern; add to `_profile_overridden`; log them
   in the `[PROFILE]` line so every data run is self-describing.

2. **Level helper** `_psi_level(some, full, thresholds) -> NONE/MODERATE/CRITICAL`,
   a direct transliteration of the harness `CalculatePressureLevel`: `CRITICAL` if
   `some >= critical or full >= full_critical`; `MODERATE` if `some >= moderate`;
   else `NONE`.

3. **Rework `_start_psi_monitor`:** read both `some` and `full` avg10; compute the
   level; track `prev_level`; apply the notify discipline ported from the harness
   FSM (act on entry; while sustained, re-act only after a cooldown; hysteresis so
   it does not flap NONE<->MODERATE). Graduated action: `MODERATE -> _request_async_gc()`
   (existing, non-blocking); `CRITICAL -> _request_critical_reclaim()` (new).

4. **CRITICAL wiring** mirrors `_request_async_gc`: a module-level
   `_request_critical_reclaim()` sets a `_critical_reclaim_pending` flag; the
   existing 250 ms drain `QTimer` also drains it and calls
   `self._purge_renderer('psi-critical')` on the Qt main thread (so CDP/socket I/O
   stays off the monitor thread and reuses the gated, rate-limited path).

## Telemetry (the chromium-validation payload)

On every **level transition**, one structured, greppable line:

```
[PSI] level=MODERATE some=12.3 full=0.0 rss_mb=842 swap_mb=120 action=async_gc
```

Plus a low-rate **heartbeat** (~60 s) logging the same fields even at `NONE`, so
the full PSI trajectory is sampled without spamming. Fields chosen to answer the
validation questions: do the trip points fire sensibly (frequency of each level;
is CRITICAL rare and genuine), are there false trips (MODERATE with low RSS / no
swap), and does the level track memory state (rss/swap correlated with level).

**Feedback loop to chromium:** collect `[PSI]` lines from `logs/wrapper_system.log`
across real sessions (`grep '\[PSI\]'` is directly parseable, or reuse the CSV
shape of `chromium-linux-mempressure/harness/sample_workload.sh`); analyze
fire-frequency, false-trip rate, and RSS correlation; confirm or nudge `some 10/40,
full 5`, recording the result back in the chromium project's
`pre-build-calibration.md` and the open-questions threshold item.

## Tests (`tests/test_qt_cdp_listener_audit.py` or new `tests/test_psi_monitor.py`)

- Boundary cases mirroring the harness: `some 9 -> NONE`, `10 -> MODERATE`,
  `40 -> CRITICAL`, `full 5 -> CRITICAL`.
- No-flap: sustained MODERATE re-acts only on cooldown; NONE<->MODERATE hysteresis.
- Env-override parsing (defaults 10/40/5; overrides applied).
- Static-analysis style, consistent with the existing wrapper audit tests.

## Acceptance & verification

- Classifies NONE/MODERATE/CRITICAL from `some`+`full`; MODERATE -> async GC,
  CRITICAL -> gated `_purge_renderer`; thresholds env-tunable; no flapping;
  degrades gracefully; skips kernels `< 4.20`.
- Live: induce pressure (`stress-ng --vm`), confirm graduated actions fire and the
  `[PSI]` lines capture the transition + RSS; confirm a normal session produces a
  clean heartbeat trajectory.
- Tests green; cherry-picked to develop (`-x`); branch retained for the #14 PR.

## Safety / rollback

Confined to the daemon-thread monitor (already `try/except`-wrapped) plus one
drain-timer branch. Mis-tuned thresholds are env-overridable or revertible via the
single function. No change to the existing RSS-ceiling/idle purge paths (#106)
beyond adding `psi-critical` as a caller.
