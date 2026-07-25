# Upstream Issue Draft: perf-agent-finalize-in-place

**File on:** `odysseus-dev/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/perf-agent-finalize-in-place.md`
**Branch:** `perf/agent-finalize-in-place`
**Type:** Performance

---

## Title

`[Performance] Agent finalize path discards entire streamed DOM tree and rebuilds from scratch`

---

## Body

**Install method:** Docker / manual Python

**OS / device:** Any

**Problem:**

When a thinking-block response finishes, the agent finalize block in `chat.js` discards the incrementally-built streaming DOM tree and replaces it with a fresh render:

```javascript
if (_liveReplyEl && _finalReply) {
  var _replyHtml = markdownModule.mdToHtml(
    markdownModule.squashOutsideCode(_finalReply));
  _liveReplyEl.innerHTML = _replyHtml;
```

At this point, `_liveReplyEl._streamRenderer` already contains the correct incremental content built during streaming. The `innerHTML` assignment:

1. Parses the entire final reply through marked/DOMPurify: full O(n) re-render.
2. Destroys the entire streamed DOM subtree; every node is detached into Oilpan.
3. Creates an equal-sized new DOM subtree from the parse output.

This is one full response-worth of detached Oilpan nodes per agent exchange. In a long session with many thinking-block responses, these subtrees accumulate as GC pressure faster than Oilpan's cooperative collector can reclaim them.

**Impact:**

In a 20-round agent session with thinking blocks, this pattern creates 20 full response DOM subtrees as garbage during finalization, in addition to the streaming allocation from the response itself. For large responses (10K+ tokens), each discarded subtree can hold thousands of DOM nodes.

**Proposed fix:**

When `_liveReplyEl._streamRenderer` exists, sync it to the final post-processed text and freeze it in-place instead of replacing the DOM. `update(_finalReply)` syncs the renderer to the final text (thinking-block extraction may trim or reformat relative to the last streamed token). `finalize()` freezes the remaining live tail and removes the tail marker. The `else` branch preserves the existing full-render path for non-streaming cases.

**Affected file:** `static/js/chat.js`: `_liveReplyEl.innerHTML` assignment in the agent finalize block
