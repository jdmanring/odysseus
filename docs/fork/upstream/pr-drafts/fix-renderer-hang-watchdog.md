# PR Draft: fix/renderer-hang-watchdog -> odysseus-dev/odysseus:dev

**Branch:** `fix/renderer-hang-watchdog`
**Status:** Ready to file — **stacks on `feat/qt-native-linux-app`**, file that first
**Base:** cut from `upstream-mirror`

---

## Title

`fix(wrapper): detect a wedged renderer main thread and auto-recover`

---

## Summary

### Problem

QtWebEngine has **no hung-renderer signal**. `renderProcessTerminated` fires only
when the process dies. A main-thread deadlock leaves the process alive and the
app permanently half-frozen with nothing reported.

Observed live: `pthread_cond_wait` inside `libQt6WebEngineCore`, zero JS
execution contexts, and the compositor still painting hover highlights — so the
window looked responsive while nothing could execute.

### Fix

Probe liveness with a `runJavaScript` ping. Its callback is serviced by the
renderer main thread, so a wedged thread cannot answer it. That makes absence of
a pong a direct signal rather than an inference.

The detection core lives in `qt_watchdog.py`, which is **Qt-free and unit-tested
with a fake clock** — the hang logic is decided by tests, not by waiting on a
real renderer.

Deliberately conservative, because a false positive reloads the user's page:

- a hang requires **both** 3+ consecutive unanswered pings **and** 35 s of silence
- recovery is cooldown-limited to 300 s, so a renderer that wedges repeatedly
  cannot thrash in a reload loop
- `loadFinished` counts as a pong

### Also in this branch

`fix(wrapper): read hang silence before record_recovery resets the pong clock` —
the `[HANG]` log line read `silence_s()` *after* `record_recovery()` had already
reset the pong clock, so a real 50 s hang logged `unresponsive 0s`. Captured
first now, with a static regression test.

---

## Verification

**Validated live by SIGSTOP**, not only by unit test: the renderer was stopped
for 50 s, which exercised the whole chain end to end — detection, CDP
`Page.reload`, and the `WebAction.Reload` fallback, which is what actually
recovered after CDP failed against the stopped process. That fallback existing
is the reason the recovery works at all, and a unit test would not have found it.

`122 passed` across the branch's test files, measured 2026-08-03.

---

## Scope

`qt_watchdog.py` (new, Qt-free), wrapper wiring, and its tests.
