# PR Draft: perf/round-finalize-inplace → pewdiepie-archdaemon/odysseus:dev

**Branch:** `jdmanring/odysseus:perf/round-finalize-inplace`
**Issue:** [#77](https://github.com/jdmanring/odysseus/issues/77) (fork tracking)
**Status:** Ready to file

---

## Title

`perf(chat): finalize agent round content in-place to avoid double DOM rebuild`

---

## Summary

### Problem

In multi-round agent sessions with tool calls, each text round's DOM is rebuilt
via `innerHTML` up to twice:

**Reset 1 — at `tool_start`** (line ~2045):

```javascript
var _contentEl3 = _ensureStreamLayout(_body3);
_contentEl3.style.minHeight = '';
_contentEl3.innerHTML = markdownModule.processWithThinking(
  markdownModule.squashOutsideCode(dt));
```

At this point `_contentEl3` is the exact `.stream-content` element that the
streaming renderer was incrementally building into. `_ensureStreamLayout` returns
the same element. The `innerHTML` assignment destroys all the incrementally built
DOM nodes and reconstructs the identical content from scratch.

**Reset 2 — at final completion with sources/findings** (line ~2703):

```javascript
_body4.innerHTML = (_sourcesData ? _buildSourcesBox(...) : '')
  + markdownModule.processWithThinking(markdownModule.squashOutsideCode(finalDisplay))
  + (_findingsData ? chatRenderer.buildFindingsBox(_findingsData) : '');
```

This wipes the entire `.body` — including the content that was finalized at Reset 1
— and rebuilds it again. For a 5-round session, this pattern creates approximately
10 discarded DOM subtrees per session.

### Fix

**Reset 1**: Check whether `_contentEl3._streamRenderer` is still active. If so,
call `.finalize()` in-place and null the reference. The frozen nodes remain in the
`.stream-content` div without being discarded. Falls back to `innerHTML` when no
renderer is present (thinking-only rounds, degraded renderer path).

```javascript
if (_contentEl3._streamRenderer) {
  _contentEl3._streamRenderer.finalize();
  _contentEl3._streamRenderer = null;
  console.log('[chat] round-finalize: tool_start in-place');
} else {
  _contentEl3.innerHTML = markdownModule.processWithThinking(
    markdownModule.squashOutsideCode(dt));
}
```

**Reset 2**: Check whether `.stream-content` already has child nodes from Reset 1's
in-place finalization. If so, inject sources and findings as siblings
(`insertBefore` / `insertAdjacentHTML`) rather than wiping `_body4.innerHTML`.
Falls back to full innerHTML when no in-place content is detected.

```javascript
var _streamContentEl = _body4.querySelector('.stream-content');
var _hasInPlaceContent = !!(_streamContentEl && _streamContentEl.childNodes.length > 0);
if (_hasInPlaceContent) {
  console.log('[chat] round-finalize: sources in-place');
  if (_sourcesData) {
    var _srcEl = document.createElement('div');
    _srcEl.innerHTML = _buildSourcesBox(_sourcesData, _sourcesType, _wasExpanded);
    _body4.insertBefore(_srcEl.firstChild || _srcEl, _streamContentEl);
  }
  if (_findingsData) {
    _body4.insertAdjacentHTML('beforeend', chatRenderer.buildFindingsBox(_findingsData));
  }
} else {
  _body4.innerHTML = ...;
}
```

### Performance impact

For a 5-round agent session with sources:
- **Before:** ~10 innerHTML assignments (2 per round: tool_start + finalize)
- **After:** 0 innerHTML assignments for content already in the DOM; sources/findings
  injected as single-element inserts

The log lines route through `javaScriptConsoleMessage` into `wrapper_system.log`
on the Qt wrapper, allowing in-app verification that the in-place path is being
taken.

---

## Files changed

- `static/js/chat.js` — Reset 1: renderer-aware finalize at `tool_start`; Reset 2:
  sibling injection when in-place content exists

## Tests

13 static-analysis tests in `tests/test_chat_round_finalize_js.py`:

Reset 1:
- `_contentEl3._streamRenderer` checked before `innerHTML`
- `.finalize()` called in renderer branch
- `._streamRenderer = null` in renderer branch
- `innerHTML` fallback in else branch
- `innerHTML` in else branch (not renderer branch)
- `hljs` highlight called after both branches
- Log line `[chat] round-finalize: tool_start in-place` present

Reset 2:
- `.stream-content` querySelector present
- `_hasInPlaceContent` guard present
- Sources injected via `_body4.insertBefore` (not innerHTML)
- Findings injected via `insertAdjacentHTML('beforeend'`
- Full re-render fallback present
- Log line `[chat] round-finalize: sources in-place` present

## Notes

- Reset 1 fix: only fires when `_streamRenderer` is active on `_contentEl3`. If the
  round had no text tokens (thinking-only), `_contentEl3._streamRenderer` is null
  and the innerHTML fallback runs. The existing `else { roundHolder.style.display = 'none' }`
  branch is unchanged.
- Reset 2 fix: `_hasInPlaceContent` detects both Reset 1 in-place finalization AND
  the existing fast-path finalize+unwrap (`perf/streaming-final-render`). The check
  is structural (has child nodes) rather than relying on a flag, so it composes
  correctly with both paths.
- Depends on `fix/dom-oom-virtualization` for multi-round agent session testing,
  but is independently correct without it.
