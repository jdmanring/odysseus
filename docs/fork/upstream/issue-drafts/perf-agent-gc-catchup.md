# Upstream Issue Draft: perf-agent-gc-catchup

**File on:** `pewdiepie-archdaemon/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/perf-agent-gc-catchup.md`
**Branch:** `perf/agent-gc-catchup`
**Type:** Performance

---

## Title

`[Performance] GC lockout creates blind spot during rapid agent tool-call sequences`

---

## Body

**Install method:** Docker / manual Python / Qt wrapper (most visible in embedded Chromium)

**OS / device:** Any; most impactful in embedded Chromium (Qt WebEngine, Electron) where Oilpan's GC is not triggered by OS memory pressure

**Problem:**

In embedded Chromium environments, `--expose-gc` + `gc({ type: 'major', execution: 'async' })` in the `finally` block is the only mechanism that causes detached DOM nodes to be collected between responses. The `_gcPending` lockout (5000ms window) prevents overlapping GC cycles, which is correct. However, it creates a blind spot:

```
T=0s   Response 1 → gc() dispatched → _gcPending = true
T=2s   Response 2 arrives → gc() BLOCKED (correct)
T=4s   Response 3 arrives → gc() BLOCKED
T=6s   Response 4 arrives → gc() BLOCKED
T=5s   _gcPending resets to false ← no catch-up; responses 2/3/4 uncollected
```

When 4 tool responses arrive in quick succession (common in multi-step agent sessions), only one GC cycle fires. The other three responses' detached DOM nodes accumulate without collection.

**Impact:**

Memory grows monotonically during agent sessions even though `gc()` fires after each batch. Reducing the lockout window alone doesn't solve this — responses can arrive faster than any lockout period short enough to be useful.

**Proposed fix:**

Add a `_gcMissed` catch-up flag. When a response arrives while `_gcPending` is true, set `_gcMissed = true`. When the primary cycle completes, if `_gcMissed` is set, immediately dispatch one catch-up GC cycle (with its own 3000ms lockout to prevent stacking). This guarantees that a burst of N rapid responses receives at most 2 GC cycles (primary + catch-up) rather than exactly 1, without creating a cascade.

Separately, reduce the lockout from 5000ms to 3000ms. `gc({ type: 'major', execution: 'async' })` runs incremental slices during idle and does not block the renderer. A 3s window is sufficient for a full sweep over 50k–200k Oilpan nodes in a typical long-session heap.

**Affected file:** `static/js/chat.js` — GC scheduling block in `finally`
