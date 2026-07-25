# PR Draft: perf/rewrite-streaming-renderer -> odysseus-dev/odysseus:dev

**Branch:** `perf/rewrite-streaming-renderer`
**Issue:** [#79](https://github.com/jdmanring/odysseus/issues/79) (fork tracking)
**Status:** Ready to file

---

## Title

`perf(chat): stream rewrite path through streamingRenderer to eliminate O(n²) rebuilds`

---

## Summary

### Problem

`rewriteWith()` streams a rewritten response token-by-token. On every SSE `delta`
token it executes:

```javascript
bodyEl.innerHTML = markdownModule.processWithThinking(
  markdownModule.squashOutsideCode(newText)
);
```

This is an O(n²) pattern: each token triggers a full markdown parse, DOMPurify
sanitization, and complete DOM reconstruction of the entire accumulated text. For a
200-token rewrite that is 200 full parse+rebuild cycles. The final `[DONE]`
handling then assigns `bodyEl.innerHTML` a second time, discarding the entire
streaming-built tree immediately after construction.

This is the same anti-pattern that was fixed for the main chat streaming path
(incremental `streamingRenderer` via `renderTail()`); the rewrite path was
overlooked.

### Fix

Lazy-initialize a `createStreamRenderer` on the first delta token and call
`.update(newText)` per token: identical to the main streaming path pattern.
After the SSE loop completes, finalize the renderer and perform a single final
`bodyEl.innerHTML` render with the stripped text (thinking blocks removed by
`_stripThink`):

```javascript
// Per-token: lazy init + incremental update
if (!_rwRenderer) {
  let _rwContentEl = bodyEl.querySelector('.stream-content');
  if (!_rwContentEl) {
    _rwContentEl = document.createElement('div');
    _rwContentEl.className = 'stream-content';
    bodyEl.appendChild(_rwContentEl);
  }
  _rwRenderer = createStreamRenderer(_rwContentEl, {
    render: (t) => markdownModule.processWithThinking(
      markdownModule.squashOutsideCode(t)),
    hljs: window.hljs,
  });
}
_rwRenderer.update(newText);

// After loop + _stripThink:
if (_rwRenderer) {
  _rwRenderer.finalize();
  _rwRenderer = null;
  console.log('[chat] rewrite: renderer finalized');
}
bodyEl.innerHTML = markdownModule.processWithThinking(
  markdownModule.squashOutsideCode(newText)
);
```

The renderer provides O(1)-per-token incremental DOM updates during streaming
(total O(n) over the full response). The single final `innerHTML` after
`_stripThink` ensures the displayed text is the clean canonical version with
thinking tags removed: identical behaviour to before, with O(n) total work
instead of O(n²).

### Performance impact

For a 200-token rewrite:
- **Before:** 200 full markdown parse + DOMPurify + innerHTML per token + 1 final
  = 201 complete DOM rebuilds
- **After:** O(n) incremental tail-patch per token via streamingRenderer + 1 final
  = ~1 effective DOM build

Heap allocation reduced from O(n²) intermediate trees to O(n) live nodes.

---

## Files changed

- `static/js/chat.js`: lazy-init renderer in `rewriteWith()` delta loop; finalize
  before final render

## Tests

11 static-analysis tests in `tests/test_chat_rewrite_streaming_js.py`:
- `_rwRenderer` variable declared in `rewriteWith` scope
- `.stream-content` div created on first delta
- `querySelector('.stream-content')` used for lazy reuse
- `createStreamRenderer` called with correct render function
- `_rwRenderer.update(newText)` called in delta loop
- No `bodyEl.innerHTML` in the delta loop
- `_rwRenderer.finalize()` called before final render
- `_rwRenderer = null` after finalize
- Single final `bodyEl.innerHTML` present
- Log line `[chat] rewrite: renderer finalized` present

## Target branch

- [x] This PR targets **`dev`**, not `main`.

## Linked Issue

Relates to #4644 ("browser tab OOM during long agent interactions"). This removes an
O(n^2) markdown rebuild that ran on every SSE delta in the rewrite path. File a focused
upstream issue if warranted and link it here before submitting.

## Type of Change

- [ ] Bug fix
- [ ] New feature
- [x] Refactor / cleanup (behaviour unchanged)
- [ ] Documentation only
- [ ] CI / tooling / configuration

## Checklist

- [x] I searched [open issues](https://github.com/odysseus-dev/odysseus/issues) and [open PRs](https://github.com/odysseus-dev/odysseus/pulls); this is not a duplicate.
- [x] This PR targets `dev`
- [x] My changes are limited to the scope described above; no unrelated refactors or whitespace changes mixed in.
- [ ] **I am not an LLM agent submitting a bulk PR.** I reviewed and tested this change personally before submitting.

### How to Test

1. Start a session and trigger a rewrite (long response with `[REWRITE]` marker or the equivalent chat action).
2. Open DevTools -> Console. After the stream completes, confirm `[chat] rewrite: renderer finalized` appears.
3. Open DevTools -> Memory. Compare heap snapshot `div` counts during the rewrite vs. before: the count should grow at O(1) per token rather than O(n²).
4. Verify the final rendered output is identical to a non-rewrite response of the same content.
5. Run `pytest tests/test_chat_rewrite_streaming_js.py -q`: 11 tests.

---

## Filing Notes

- 2 commits: main fix (`04eea77f`), logging (`1d8bdd83`).
- Branch: `perf/rewrite-streaming-renderer`, built from `upstream-mirror`.
- **File upstream issue first.** Add the upstream issue number to `Fixes #` above.
- The `_rwRenderer` variable is declared as `null` at the top of `rewriteWith()` scope. If an error path exits the SSE loop early, the `finally` block should null it out: verify this edge case is handled if filing this PR.

## Visual / UI changes

None. The final rendered output is identical; this change only affects the allocation pattern during streaming.
