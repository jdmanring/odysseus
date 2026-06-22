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

## Target branch

- [x] This PR targets **`dev`**, not `main`.

## Linked Issue

Fixes # <!-- [add upstream issue number before filing] -->

## Type of Change

- [ ] Bug fix
- [ ] New feature
- [x] Refactor / cleanup (behaviour unchanged)
- [ ] Documentation only
- [ ] CI / tooling / configuration

## Checklist

- [x] I searched [open issues](https://github.com/pewdiepie-archdaemon/odysseus/issues) and [open PRs](https://github.com/pewdiepie-archdaemon/odysseus/pulls); this is not a duplicate.
- [x] This PR targets `dev`
- [x] My changes are limited to the scope described above; no unrelated refactors or whitespace changes mixed in.
- [ ] **I am not an LLM agent submitting a bulk PR.** I reviewed and tested this change personally before submitting.

### How to Test

1. Start the app with agent mode active (tool calls enabled).
2. Run a multi-round agent session — 3+ rounds, with tool calls and text in each round.
3. In `wrapper_system.log` (or DevTools Console), confirm:
   - `[chat] round-finalize: tool_start in-place` appears once per round (Reset 1 in-place path firing)
   - `[chat] round-finalize: sources in-place` appears for rounds with sources (Reset 2 in-place path)
4. Open DevTools → Memory. Confirm `div` count grows more slowly than before for multi-round sessions.
5. Verify final rendered content and source boxes are identical to the previous behavior.
6. Run `pytest tests/test_chat_round_finalize_js.py -q` — 13 tests.

---

## Filing Notes

- 2 commits: in-place fixes (`1ee51846`), logging (`06cb0a2e`).
- Branch: `perf/round-finalize-inplace` — built from `upstream-mirror`.
- **File upstream issue first.** Add the upstream issue number to `Fixes #` above.
- Reset 1 only fires when `_contentEl3._streamRenderer` is non-null. In thinking-only rounds (no text tokens), `_streamRenderer` is null and the existing `innerHTML` path runs. This is expected.
- Reset 2's `_hasInPlaceContent` check is structural (child node presence), not flag-based. It composes correctly with both the Reset 1 in-place path and the existing `perf/streaming-final-render` fast-path finalize.

## Visual / UI changes

None. The rendered output and source box layout are identical; this change only affects how many intermediate DOM trees are created during multi-round finalization.
