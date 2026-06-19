# Issue Draft: fix/chat-auto-scroll-threshold

**Title:** chat: auto-scroll aborts prematurely when large content arrives

**Labels:** bug

---

## Body

### Description

The chat history auto-scroll stops following the bottom when a large content block arrives —
a code block with syntax highlighting, an image, or rich markdown with many lines. The user
sees the conversation "drift off" the bottom and must scroll down manually.

### Root Cause

`_smoothScrollStep()` in `static/js/ui.js` guards against forcing the user back to the bottom
if they have intentionally scrolled up. The guard checks:

```javascript
if (diff > 300) {
  _scrollRafId = null;
  return;
}
```

`diff` is `scrollHeight - clientHeight - scrollTop` (distance from current position to
bottom). When large content arrives, `scrollHeight` can jump by several hundred pixels in a
single animation frame. If the user was near the bottom, this sudden increase pushes `diff`
over 300px, falsely triggering the guard — the scroll stops even though the user never
scrolled up.

### Impact

Every message containing a code block or image can cause the chat to lose its scroll
position. Users must manually scroll to bottom after every AI response that includes code.

### Proposed Fix

Replace the rigid 300px threshold with a viewport-scaled adaptive threshold:

```javascript
const viewportHeight = box.clientHeight;
const maxAllowedDiff = Math.max(300, viewportHeight * 1.5);
if (diff > maxAllowedDiff) {
  _scrollRafId = null;
  return;
}
```

`Math.max(300, viewportHeight * 1.5)` keeps the 300px minimum (sufficient for genuine user
scrolling on small viewports) but scales up for larger viewports where layout shifts from
big content blocks are expected to be proportionally larger.

### Affected File

`static/js/ui.js` — `_smoothScrollStep()` function
