# Upstream Issue Draft: perf-hljs-deferred-highlight

**File on:** `odysseus-dev/odysseus`
**Related PR draft:** *(PR draft covers `deferHighlightAll` calls — part of GC micro-improvements series)*
**Branch:** `perf/hljs-deferred-highlight`
**Type:** Performance

---

## Title

`[Performance] Synchronous hljs.highlightElement blocks main thread for off-screen code blocks`

---

## Body

**Install method:** Docker / manual Python

**OS / device:** Any

**Problem:**

`window.hljs.highlightElement(block)` is called synchronously when messages containing code blocks are inserted into the DOM — including on history load, session switch, and background stream completion. For code blocks that are outside the viewport (scrolled out of view), this work is invisible to the user but still blocks the main thread.

`highlightElement` runs the highlight.js tokenizer synchronously in the main thread. For a 300-line code block this can take 5–20 ms. When a session loads with 20 messages containing code blocks, that is up to 400 ms of synchronous highlighting work on the main thread before the page is interactive.

Additionally, there are currently 8 call sites in `chat.js` that call `highlightElement` via a `forEach` loop, bypassing the existing `deferHighlightAll` utility that was introduced for exactly this purpose.

**Root cause:**

`deferHighlightAll(container)` (in `hljsDefer.js`) uses a single shared `IntersectionObserver` (rootMargin: 200px) to queue highlighting only when blocks scroll into the viewport. The 8 remaining direct `window.hljs.highlightElement` forEach loops in `chat.js` were not migrated when `deferHighlightAll` was introduced.

**Impact:**

- History loads with many code blocks stall the main thread for several hundred milliseconds.
- Completed background streams (off-screen by definition) highlight their code blocks synchronously at completion rather than when the user navigates to them.
- Users on slower machines or in embedded Chromium (Qt wrapper, Electron) experience noticeable jank on session switch.

**Proposed fix:**

Replace all 8 `window.hljs.highlightElement` forEach loops in `chat.js` with `deferHighlightAll(container)`. Blocks that are in the viewport at insertion time highlight within one observer tick (~16 ms) — imperceptible. Off-screen blocks highlight when scrolled into view.

**Affected file:** `static/js/chat.js` — 8 `highlightElement` call sites
