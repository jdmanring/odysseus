# Upstream Issue Draft: perf-gc-micro-improvements

**File on:** `pewdiepie-archdaemon/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/perf-gc-micro-improvements.md`
**Branch:** `perf/gc-micro-improvements` (squashOutsideCode), `perf/hljs-deferred-highlight` (deferHighlightAll)
**Type:** Performance

---

## Title

`[Performance] Three small GC improvements: squashOutsideCode allocation, deferred highlight migration, background stream cleanup on session switch`

---

## Body

**Install method:** Docker / manual Python

**OS / device:** Any

**Problem:**

Three independent, low-impact allocation sources that each add a small amount of unnecessary GC pressure during streaming or session switching.

**A. `squashOutsideCode` allocates on every streaming token (~30 fps):**

`squashOutsideCode` in `static/js/markdown.js` is called on every SSE token during streaming. For the common case — plain-text responses with no code blocks — it unconditionally executes:

```javascript
const parts = str.split(/```/);  // allocates array
// ... modify even-indexed parts ...
return parts.join('```');         // allocates string
```

When no code fences are present, the split array has exactly one element and the join is a no-op copy. The allocation is pure waste. A `str.includes('```')` guard short-circuits the entire split/join path and applies the three normalization regexes directly to the full string instead — semantically equivalent because all characters are "outside code" when no fences exist.

**B. Seven remaining direct `hljs.highlightElement` calls bypass `deferHighlightAll`:**

`deferHighlightAll(container)` was introduced in `perf/hljs-deferred-highlight` to use an `IntersectionObserver` to defer highlighting until blocks are near the viewport. Seven `window.hljs.highlightElement` forEach loops in `chat.js` were not migrated. Four of these highlight containers that may be entirely off-screen (history loads, completed background streams). These should all use `deferHighlightAll`.

**C. Completed background stream Map entries not purged on session switch:**

`_purgeStaleBackgroundStreams()` clears `_backgroundStreams` Map entries for completed/error streams. It is called only in `handleChatSubmit`. When the user switches sessions between submits, completed entries accumulate in the Map with their `accumulated` text already cleared but their Map entry still present. These entries are cleaned up on the next submit; adding one call at the top of `checkBackgroundStream` (invoked on every session switch) closes the gap.

**Each improvement is small but composes with the larger GC-reduction series** (streaming throttle, rendertail text path, in-place finalization). `squashOutsideCode` runs on every SSE token, so even a few words of savings per token adds up across a full session.

**Affected files:**
- `static/js/markdown.js` — `squashOutsideCode`
- `static/js/chat.js` — 7 `highlightElement` sites; `checkBackgroundStream`
