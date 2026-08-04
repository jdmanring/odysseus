# PR Draft: perf/tool-bubble-inplace -> odysseus-dev/odysseus:dev

**Branch:** `perf/tool-bubble-inplace`
**Status:** Ready to file
**Base:** cut from `upstream-mirror`, 2 files, +123/-9

---

## Title

`perf(streaming): patch the tool bubble in place at completion`

---

## Summary

### Problem

When a tool call completes, the handler replaced the tool bubble's entire
`innerHTML`. That detaches the whole subtree — header, icon, wave animation,
elapsed timer, content — to change what is mostly a status icon and remove two
spans.

One detached subtree per tool call, and an agent turn can make many.

### Fix

Cache the element references on each tool node **at creation**, then at
`tool_output` update only what actually changes: patch the icon text, remove the
wave and elapsed spans, null the wave reference, and append the status/chevron.

The structural header nodes are reused rather than rebuilt.

**Content still replaces `_toolContentEl.innerHTML`**, deliberately: the command,
output and diff are genuinely new on completion, so there is nothing to reuse
there. This PR reuses the parts that are unchanged and rebuilds the parts that
are not, rather than claiming to eliminate the rebuild entirely.

### The ordering that makes it work

Refs are cached **immediately after `innerHTML`, before `appendChild`**. Caching
after insertion would work today and break the first time the insertion path
changes; the tests pin the order.

---

## Verification

**11 passed**, measured 2026-08-03. The static tests lock all four element refs
being cached at the right point, and that the completion handler patches rather
than replacing — including a guard that the old full-`innerHTML` replace has not
returned.

One of those assertions was **corrected in this branch**:
`test_tool_complete_removes_elapsed_span` previously passed on
`_toolWaveEl.remove()`, which appears earlier in the same body, so it did not
actually test the elapsed span. It is now a positional check (the elapsed-span
`querySelector` is followed by `.remove()`).

---

## Scope

`static/js/chat.js` (+38/-9) and one test file.
