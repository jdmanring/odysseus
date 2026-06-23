# Upstream Issue Draft: fix-memory-panel-listener-leak

**File on:** `pewdiepie-archdaemon/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/fix-memory-panel-listener-leak.md`
**Branch:** `fix/memory-panel-listener-leak`
**Type:** Bug / Performance
**Fork issue:** [#89](https://github.com/jdmanring/odysseus/issues/89)

---

## Title

`[Brain] Memory list accumulates event listeners across render passes, causing permanent RSS growth`

---

## Body

**Install method:** Docker / manual Python / Qt wrapper

**OS / device:** All platforms (most visible in Qt wrapper where Chromium's Oilpan GC receives no OS memory pressure signals)

**Summary:**

Opening the Brain panel and interacting with the memory list produces RSS growth of ~956 MiB that does not reclaim after the panel is closed. Three distinct sources are responsible.

**Root cause 1 — document.addEventListener accumulation (primary):**

`renderMemoryList()` registers a `document`-level click listener per memory item per render call to handle outside-click dropdown dismissal. The listener has `{ once: false }` (the default), so it never self-removes. With 50 items and 10 render passes (from CRUD operations, filter changes, etc.), 500 listeners accumulate on `document`. Each listener holds a closure over a dropdown DOM node; when the list is cleared via `memoryList.innerHTML = ''`, those dropdown closures prevent the GC from collecting the old nodes.

**Root cause 2 — no cross-render listener cleanup:**

Item-level listeners (checkbox, click, dblclick, pointer events, menu button) are registered on each item during `renderMemoryList()`. When `innerHTML = ''` clears the list, the closure captures (dropdown references, memory IDs) remain in memory until Oilpan runs a major GC cycle. In Qt-embedded Chromium, which never receives OS memory pressure signals, this major cycle is rarely triggered.

**Root cause 3 — animations running while panel is hidden:**

The `::after` sweep animation on `.memory-item` continues running when `#memory-modal` receives the `.hidden` class, keeping compositor tile allocations alive for the entire hidden list.

**Fix summary:**

1. `AbortController` per render pass: abort the previous controller before `innerHTML = ''` to release all item-level listener closures immediately.
2. Move the document click listener inside the `menuBtn` click handler with `{ once: true, signal }`. This changes N-per-render accumulation to 1 listener per open dropdown, self-removing on first click.
3. CSS rule: `#memory-modal.hidden #memory-list .memory-item::after { animation-play-state: paused; }` halts compositor tile work when the panel is not visible.
4. MutationObserver on the modal element to close any open dropdown and trigger `gc()` (feature-detected — only available with `--js-flags=--expose-gc`) when the panel is hidden.

**Expected behavior:**

RSS should not grow significantly from repeated Brain panel opens/closes or memory list interactions, and should recover within a GC cycle after the panel is closed.

**Observed behavior:**

QtWebEngineProcess RSS reaches ~956 MiB after normal use of the memory list and does not recover after closing the Brain panel.

**Reproduction:**

1. Open the Browser DevTools memory profiler (or note RSS via `ps aux`).
2. Open the Brain panel and interact with the memory list: hover, open item menus, change filters.
3. Close the panel. Observe RSS does not decline.
4. Repeat 3–4 times and note continued growth.

---
