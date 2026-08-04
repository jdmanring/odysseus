# PR Draft: perf/qt-psi-graduated-reclaim -> odysseus-dev/odysseus:dev

**Branch:** `perf/qt-psi-graduated-reclaim`
**Status:** Ready to file - **stacks on `feat/qt-native-linux-app`**, file that first
**Base:** cut from `upstream-mirror`, 11 files, +2011/-11

**Supersedes `perf/renderer-memory-reclaim`**, which was a strict subset (zero
commits unique to it) and has been deleted.

---

## Title

`perf(qt): graduated PSI reclaim, with a Qt-free testable detection core`

---

## Summary

### What this fixes, and how it was established

The renderer climbs unbounded in the desktop wrapper, and the reclaim that was
supposed to bound it **did nothing**. Measured live over CDP:

| call | result |
|---|---|
| `simulatePressureNotification('critical')` | **no-op** on QtWebEngine, RSS unchanged |
| `forciblyPurgeJavaScriptMemory` | reclaimed **5.2 GB / 3.7 GB** |

The wrapper's idle, periodic and focus-loss triggers were all calling the
no-op, while `gc()` touched only the ~43 MB JS pool. So the renderer reached 5+
GB with panels open and nothing in the code was obviously wrong - the API being
called simply has no effect in this embedder.

That is the core finding, and it was only reachable by measuring both calls
against a live renderer rather than trusting the API's name.

### The reclaim

`_purge_renderer` gated on an RSS ceiling with a rate limit, fired on genuine
idle and focus-loss rather than on a timer. Verified live in
`logs/wrapper_system.log`:

```
forcible purge (post-interaction-idle): ok RSS 1232632 -> 608360 kB
```

Two further corrections that are easy to get wrong and are worth reviewing:

- **Single-shot reclaim was not enough.** The original re-armed only on mouse
  move, so a walk-away filled RAM. A repeating sustained-idle timer bounds memory
  regardless of whether the user returns.
- **The idle threshold must be a real away-gap.** At 3 s it fired during ordinary
  reading pauses, and the purge blocks the renderer ~1 s - landing on a click, or
  dropping a mid-drag mouseup, left Chromium's left-button state stuck. Default
  is now 60 s, the W3C/WICG Idle Detection API's own minimum for calling a user
  idle, rather than a guessed number.

### Why the PSI core was extracted

`qt_psi.py` pulls the PSI detection logic - parse, level mapping, the three-arm
notify FSM, meminfo reads, the daemon monitor and event cell - out of
`qt_wrapper.py`. None of it needed Qt, but living beside module-level PyQt
imports made it **unimportable in the server venv**, so its tests were not
running. Extraction is what makes the detection logic testable at all.

---

## Verification

**98 passed**, measured 2026-08-03, across the branch's test files.

Two of those assertions were **fixed today**: both reclaim defaults became
conditional when the low-resource profile landed (`'20' if _low_resource else
'60'`) and the ceiling call wrapped across lines, so regexes matching only the
single-line literal form failed against correct source. They now accept both
forms, still hold the standard default to the 60 s floor, and additionally assert
the low-resource default is a deliberate tightening.

---

## Scope

`qt_psi.py` (new, Qt-free), `qt_wrapper.py`, `static/js/qt-bridge.js`,
`static/js/colorPicker.js`, and 5 test files.
