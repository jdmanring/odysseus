# PR Draft: perf/agent-finalize-in-place → odysseus-dev/odysseus:dev

**Branch:** `perf/agent-finalize-in-place`
**Issue:** [#74](https://github.com/jdmanring/odysseus/issues/74) (fork tracking)
**Status:** Ready to file

---

## Title

`perf(chat): finalize live-reply renderer in-place on agent path`

---

## Summary

### Problem

When a thinking-block response finishes, the agent finalize block in `chat.js` does:

```javascript
if (_liveReplyEl && _finalReply) {
  var _replyHtml = markdownModule.mdToHtml(markdownModule.squashOutsideCode(_finalReply));
  _liveReplyEl.innerHTML = _replyHtml;
```

At this point `_liveReplyEl._streamRenderer` already holds the correct incremental content
from the full streaming session. The `innerHTML = mdToHtml()` assignment:

1. Parses the entire final reply through marked/DOMPurify — full O(n) re-render
2. Destroys the entire streamed DOM subtree (detaches all its nodes into Oilpan)
3. Creates an equal-sized new DOM subtree from the parse output

This is one full response-worth of detached Oilpan nodes per agent exchange. In a long
session with many thinking-block responses, these subtrees accumulate as GC pressure
faster than Oilpan's cooperative collector can reclaim them.

### Fix

When `_liveReplyEl._streamRenderer` exists, sync it to the final post-processed text
and freeze it in-place instead of replacing the DOM:

```javascript
if (_liveReplyEl && _finalReply) {
  if (_liveReplyEl._streamRenderer) {
    _liveReplyEl._streamRenderer.update(_finalReply);
    _liveReplyEl._streamRenderer.finalize();
    _liveReplyEl._streamRenderer = null;
    console.log('[chat] live-reply: finalized in-place');
  } else {
    // No streaming renderer (e.g. fast non-streaming path): full render.
    var _replyHtml = markdownModule.mdToHtml(markdownModule.squashOutsideCode(_finalReply));
    _liveReplyEl.innerHTML = _replyHtml;
  }
  _liveReplyEl.classList.remove('live-reply-content');
  // sources/findings handling unchanged
```

`update(_finalReply)` syncs the renderer to the final post-processed text (thinking-block
extraction may trim or reformat it relative to the last streamed token). `finalize()`
freezes the remaining live tail and removes the tail marker — the same lifecycle as the
plain-response fast path in `streamingRenderer.finalize()`.

The `else` branch preserves the existing full-render path for the non-streaming case
(e.g., fast cached responses where no `_streamRenderer` was created).

### Testing

- `tests/test_chat_live_reply_finalize_js.py` — 8 static-analysis tests:
  - Renderer branch calls `update(_finalReply)` and `finalize()`
  - `update()` precedes `finalize()` (ordering)
  - `_streamRenderer` is nulled after `finalize()` (ordering)
  - A `console.log` confirms the in-place path for observability in session logs
  - Fallback branch still uses `mdToHtml` + `innerHTML` (not regressed)
  - `classList.remove('live-reply-content')` appears after both branches (shared)

## Target branch

- [x] This PR targets **`dev`**, not `main`.

## Linked Issue

Relates to #4644 ("browser tab OOM during long agent interactions"). This finalizes the
streamed agent reply in place instead of rebuilding it via `innerHTML`. File a focused
upstream issue if warranted and link it here before submitting.

## Type of Change

- [ ] Bug fix (non-breaking, fixes a confirmed issue)
- [ ] New feature (non-breaking, adds new behaviour)
- [ ] Breaking change (changes or removes existing behaviour)
- [x] Refactor / cleanup (behaviour unchanged)
- [ ] Documentation only
- [ ] CI / tooling / configuration

## Checklist

- [x] I searched [open issues](https://github.com/odysseus-dev/odysseus/issues) and [open PRs](https://github.com/odysseus-dev/odysseus/pulls); this is not a duplicate.
- [x] This PR targets `dev`
- [x] My changes are limited to the scope described above; no unrelated refactors or whitespace changes mixed in.
- [ ] **I am not an LLM agent submitting a bulk PR.** I reviewed and tested this change personally before submitting.

### How to Test

1. Start the app with agent mode active (thinking blocks enabled).
2. Complete a multi-round agent session (5+ exchanges).
3. In `wrapper_system.log`, confirm `[chat] live-reply: finalized in-place` appears once
   per agent response, confirming the in-place path fired.
4. Open DevTools → Memory. Record heap snapshots between agent responses.
   The detached node count should grow more slowly than before this patch.
5. Run `pytest tests/test_chat_live_reply_finalize_js.py -q` — 8 tests.

---

## Filing Notes

- 2 commits: main fix (`2c38aaf3`), logging + test (`ccd93c13`).
- Branch: `perf/agent-finalize-in-place` — built from `upstream-mirror`.
- **File upstream issue first.** Add the upstream issue number to `Fixes #` above.
- The `null` assignment at the later `if (_liveReplyEl && _liveReplyEl._streamRenderer)`
  guard (further down in the same function) becomes a no-op when the renderer was already
  nulled here — harmless.

## Visual / UI changes

None. The final rendered output is identical; this change only affects which code path
produces it and how many intermediate DOM nodes are created and discarded.
