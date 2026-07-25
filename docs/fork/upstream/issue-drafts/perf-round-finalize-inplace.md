# Upstream Issue Draft: perf-round-finalize-inplace

**File on:** `odysseus-dev/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/perf-round-finalize-inplace.md`
**Branch:** `perf/round-finalize-inplace`
**Type:** Performance

---

## Title

`[Performance] Multi-round agent sessions rebuild DOM twice per round via innerHTML`

---

## Body

**Install method:** Docker / manual Python

**OS / device:** Any

**Problem:**

In multi-round agent sessions with tool calls, each text round's DOM content is rebuilt via `innerHTML` up to twice before the final output is displayed:

**Rebuild 1: at `tool_start`:**

When a tool call begins, the agent's text content is "locked in" via:

```javascript
_contentEl3.innerHTML = markdownModule.processWithThinking(
  markdownModule.squashOutsideCode(dt));
```

At this point, `_contentEl3` already contains the incrementally-built streaming DOM from `_streamRenderer`. The `innerHTML` assignment discards this entire tree (all nodes detach into Oilpan) and reconstructs the identical content from scratch via `processWithThinking` (marked -> DOMPurify -> HTML string -> DOM parse).

**Rebuild 2: at final completion:**

When the round completes and sources/findings are available:

```javascript
_body4.innerHTML = (_sourcesData ? _buildSourcesBox(...) : '')
  + markdownModule.processWithThinking(...)
  + (_findingsData ? chatRenderer.buildFindingsBox(...) : '');
```

This wipes the entire `.body` element, including the content that was finalized at Rebuild 1, and reconstructs it again. For a 5-round session, this is approximately 10 `innerHTML` assignments discarding ~10 full response DOM trees.

**Impact:**

Each `innerHTML` assignment on a large response creates a full copy of the DOM subtree as garbage in Oilpan. At 10 rebuilds per 5-round session with 2K+ node responses, this is 20,000+ detached nodes per session from finalization alone: on top of the streaming allocation.

**Proposed fix:**

At Rebuild 1: check whether `_contentEl3._streamRenderer` is still active. If so, call `.finalize()` in-place. At Rebuild 2: check whether `.stream-content` already has child nodes from the in-place finalization. If so, inject sources and findings as siblings (`insertBefore`, `insertAdjacentHTML`) rather than wiping the body.

Both fixes have safe fallback paths (existing `innerHTML` for cases where no streaming renderer was active).

**Affected file:** `static/js/chat.js`, `tool_start` block and final completion block in the agent response handler
