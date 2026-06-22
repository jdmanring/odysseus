# Upstream Issue Draft: perf-tool-bubble-inplace

**File on:** `pewdiepie-archdaemon/odysseus`
**Related PR draft:** *(no dedicated PR draft — see streaming/GC series)*
**Branch:** `perf/tool-bubble-inplace`
**Type:** Performance

---

## Title

`[Performance] Tool bubble state rebuilt via innerHTML at completion instead of patched in-place`

---

## Body

**Install method:** Docker / manual Python

**OS / device:** Any

**Problem:**

When a tool call completes, the tool bubble's UI state is updated (status indicator, elapsed time display, result summary). The current implementation replaces the bubble's content via `innerHTML`, discarding the incrementally-built bubble DOM and constructing a new one.

For multi-tool-call agent sessions where each round may contain 3–5 tool calls, this is 3–5 additional `innerHTML` rebuilds per round on top of the response-text finalization rebuilds tracked in issue #77. Each rebuild detaches the current bubble subtree into Oilpan.

**Proposed fix:**

Patch the tool bubble state in-place at completion: update only the changed DOM nodes (status icon, elapsed time text, result summary) rather than replacing the entire bubble. This avoids detaching and discarding any nodes.

The bubble DOM structure is stable after initialization — only the inner content of specific elements changes on completion. Direct property writes (`textContent`, `className`) on the existing elements are sufficient.

**Affected file:** `static/js/chat.js` — tool bubble completion handler (the block that fires when `tool_output` is received for a given tool call)
