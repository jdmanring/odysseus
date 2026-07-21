# Upstream Issue Draft: perf-smooth-typing

**File on:** `odysseus-dev/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/perf-smooth-typing.md`
**Branch:** `perf/smooth-typing`
**Type:** Performance

---

## Title

`[Performance] autoResize causes 2 forced layout reflows per keystroke — input jank in embedded Chromium`

---

## Body

**Install method:** Docker / manual Python / Qt wrapper

**OS / device:** Any; most noticeable in embedded Chromium (Qt WebEngine, Electron) and lower-end hardware

**Problem:**

`autoResize` in `static/js/ui.js` fires on the textarea's `input` event and measures the textarea's natural content height using a hidden clone:

1. `getComputedStyle(textarea).lineHeight` — forces style recalculation
2. `textarea.offsetWidth` — forces a layout reflow to get the current width
3. `clone.scrollHeight` — forces a second layout reflow on the clone

This produces **2 forced DOM layout reflows per keystroke**. The browser must pause JavaScript execution to perform a full layout pass (compute element sizes, reflow descendants) before returning the requested value. At 10 keystrokes/second that is 20 forced reflows per second.

In standard browsers, the impact is small because the browser can batch reflows efficiently. In embedded Chromium environments (Qt WebEngine, Electron), the rendering pipeline has higher per-reflow overhead — each forced reflow is more expensive, and 20/second produces perceptible input lag.

**Steps to reproduce:**

1. Run the app in the Qt native wrapper (`bash build-linux-app.sh`).
2. Open a chat session and type quickly in the textarea.
3. Observe input lag, especially on longer messages where the textarea is expanding.
4. Open DevTools → Performance, record while typing. Observe "Recalculate Style" and "Layout" entries triggered by every keystroke.

**Expected:** Typing is smooth. Layout work is coalesced to at most one reflow per animation frame regardless of typing speed.

**Proposed fix:**

Replace the clone-based approach with `requestAnimationFrame`-coalesced `height:'auto'` + `scrollHeight`. The rAF guard (`_arRafId`) ensures N keystrokes within a single 16ms frame collapse to exactly one layout operation. The `height:'auto'` + `scrollHeight` approach is one read instead of two, and the clone (with its associated cloneNode + DOM insertion + positioning) is eliminated entirely.

The same rAF-coalesce pattern is already used elsewhere in the codebase (`_renderRafId` in streaming). This aligns `autoResize` with that established pattern.

**Affected file:** `static/js/ui.js` — `autoResize()` function
