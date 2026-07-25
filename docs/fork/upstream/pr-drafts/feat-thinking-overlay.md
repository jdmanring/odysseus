# feat(chat): render the Thinking indicator as a zero-footprint sticky overlay

## Problem

The live "Thinking" indicator is an in-flow `.msg` appended to `#chat-history`. Every show, replace (tool-aware label changes), and remove moves the document's bottom edge: the layout shifts, scroll position churns, and when the real reply arrives the box vanishes from flow and the content jumps again.

## Change

The indicator becomes a zero-footprint sticky overlay:

- A `height: 0; position: sticky; bottom: 8px; overflow: visible` anchor appended as the log's last child, so the document's bottom edge never moves when the indicator appears, changes, or leaves.
- The bubble is absolutely positioned above the anchor. Because the anchor is sticky inside the scroller, the indicator also stays visible at the viewport bottom while the user scrolls back through history. Previously it sat at the end of the conversation, out of view.
- `role="status"` replaces the announcement the in-flow message provided to assistive tech.
- The `agent-thinking-dots` class stays on the element and the element stays inside `#chat-history`, so every existing cleanup query and the log's `aria-busy` ownership check work unchanged.
- Deliberately no `transform` and no `will-change`: the overlay must not cost a compositor layer.
- The `scrollHistory()` call on show is dropped: nothing moves, so there is nothing to compensate.

## Verification

- Measured in the running app: `scrollHeight` and pinned bottom-distance are byte-identical across append, replace, and remove of the overlay; computed style confirms `sticky/0px`; when scrolled up, the bubble renders inside the viewport's bottom edge.
- 7 static guards (`tests/test_thinking_overlay_js.py`): overlay classes, `role=status`, not an in-flow `.msg`, no scroll call, stays inside the log, sticky zero-height CSS, no compositor-layer properties.

## Risk

Low. The element keeps its class and container, so all lifecycle interactions (removal on round completion, stream cleanup, aria-busy) are untouched; only its geometry contract changed.
