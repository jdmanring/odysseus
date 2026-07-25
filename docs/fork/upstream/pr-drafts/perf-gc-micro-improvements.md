# PR Draft: perf: reduce GC pressure: squashOutsideCode fast path, deferred hljs highlight, background stream cleanup

**Branch:** `perf/gc-micro-improvements` (squashOutsideCode), `perf/hljs-deferred-highlight` (deferHighlightAll)
**Issue:** [#82](https://github.com/jdmanring/odysseus/issues/82)
**Base:** `upstream-mirror` (latest upstream commit)

---

## Title

`perf(chat): reduce GC pressure, squashOutsideCode fast path, deferred hljs, background stream cleanup`

---

## Summary

Three targeted GC/memory improvements requiring no architectural changes:

### A. squashOutsideCode fast path (markdown.js)

`squashOutsideCode` is called at ~30 fps during streaming. For the common case,
plain-text responses with no code blocks, it was allocating a `split` array and
`join` string on every call, discarded immediately.

Add `str.includes('```')` guard that returns after applying the three normalization
regexes directly to the full string. Semantically equivalent: when no fences are
present, all characters are outside code, so normalizing the whole string gives the
same result as normalizing the sole even-indexed part. The code-fence path is unchanged.

```javascript
export function squashOutsideCode(s) {
  if (!s) return "";
  const str = String(s);
  if (!str.includes('```')) {
    return str
      .replace(/\r\n/g, '\n')
      .replace(/[ \t]+\n/g, '\n')
      .replace(/\n{3,}/g, '\n\n');
  }
  const parts = str.split(/```/);
  // ... unchanged code-fence path
```

### B. Replace all direct `window.hljs.highlightElement` calls with `deferHighlightAll` (chat.js)

`deferHighlightAll` (introduced in `perf/hljs-deferred-highlight`) uses a single
shared `IntersectionObserver` (rootMargin: 200px) to highlight `pre>code` blocks
only when they scroll into the viewport. The existing migration left 7 direct
`window.hljs.highlightElement` forEach loops in chat.js:

- stop-stream path (`currentHolder`)
- agent round finalise (`roundHolder`): two sites
- continue-message merge (`prevEl`)
- error/stop catch block (`holder`)
- variant switch (`msgElement`)
- background stream complete (`_wrap`)
- background research polling (`holder`)

4 of these 7 highlight containers that may be entirely off-screen (history loads,
completed background streams). Replaced all 7 with `deferHighlightAll(container)`.
Visible blocks still highlight within one observer tick (~16 ms): imperceptible.

### C. Purge stale background stream Map entries on session switch (chat.js)

`_purgeStaleBackgroundStreams()` sweeps `_backgroundStreams` for completed/error
entries and deletes them. It was called only in `handleChatSubmit`. Completed entries
with text cleared to `''` accumulated across session switches until the next submit.

Added a call at the top of `checkBackgroundStream`, which sessions.js invokes on
every session switch. Zero new API surface: one line added.

```javascript
export function checkBackgroundStream(sessionId) {
  _purgeStaleBackgroundStreams();   // ← added
  if (!sessionId || !_backgroundStreams.has(sessionId)) return;
```

## Files changed

- `static/js/markdown.js`: squashOutsideCode fast path (+5 −1 lines)
- `static/js/chat.js`: 7 highlightElement -> deferHighlightAll; purge on session switch (+3 −18 lines)
- `tests/test_markdown_squash_js.py`: new file, 3 tests
- `tests/test_chat_hljs_defer_js.py`: new file, 3 tests
- `tests/test_chat_gc_hint_js.py`: +1 test

## Tests

6 new static-analysis tests across 3 files:

**`tests/test_markdown_squash_js.py`** (new, 3 tests):
- `test_squash_fast_path_on_no_backticks`: `includes('```')` guard present
- `test_squash_fast_path_precedes_split`: fast path before `split()` call
- `test_squash_code_fence_path_preserved`: split+join path still present

**`tests/test_chat_hljs_defer_js.py`** (new, 3 tests):
- `test_no_direct_highlight_element_calls`: `window.hljs.highlightElement` absent
- `test_hljs_defer_import_present`: `import { deferHighlightAll` present
- `test_defer_highlight_all_call_count`: >= 8 `deferHighlightAll(` calls

**`tests/test_chat_gc_hint_js.py`** (+1 test):
- `test_check_background_stream_purges_stale`: `_purgeStaleBackgroundStreams()` at top of `checkBackgroundStream`

## Target branch

- [x] This PR targets **`dev`**, not `main`.

## Linked Issue

Relates to #4644 ("browser tab OOM during long agent interactions"). This reduces GC and
allocation pressure during streaming (a `squashOutsideCode` fast path and deferred
highlighting). File a focused upstream issue if warranted and link it here before
submitting. (Do not use the bare number from the fork tracker as an upstream issue
reference.)

## Type of Change

- [ ] Bug fix
- [ ] New feature
- [x] Refactor / cleanup (behaviour unchanged)
- [ ] Documentation only
- [ ] CI / tooling / configuration

## Checklist

- [x] I searched open issues and open PRs; this is not a duplicate.
- [x] This PR targets `dev`.
- [x] My changes are limited to the scope described above.
- [x] I actually ran the app and verified the change works end-to-end.

### How to Test

1. Load a session with plain-text responses (no code blocks) and open DevTools Performance. Confirm no `split`/`join` allocations in `squashOutsideCode` per streaming tick.
2. Load a session with code blocks from history. Confirm code highlights within ~16 ms of scrolling each block into view rather than all at once on load.
3. Open a background stream in one session, switch sessions, switch back. Confirm the completed background stream entry is no longer in `_backgroundStreams` (instrument via DevTools console or add a log).

## Filing Notes

- `perf/gc-micro-improvements` contains only the `squashOutsideCode` change.
- `perf/hljs-deferred-highlight` contains the `deferHighlightAll` migration; this PR extends that branch.
- The `checkBackgroundStream` purge can be filed as part of either branch: it is a single line and has no dependencies.
- The chatHistory.js changes (rIC signal, teardown gap) are fork-specific for now (chatHistory.js is not yet in upstream); they will ship with the DOM virtualization PR when that is filed.
