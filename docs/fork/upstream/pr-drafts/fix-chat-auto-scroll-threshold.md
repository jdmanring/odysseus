# PR Draft: fix/chat-auto-scroll-threshold

**Title:** fix(ui): adaptive threshold for chat auto-scroll drift guard

**Branch:** `fix/chat-auto-scroll-threshold` -> `odysseus-dev/odysseus:dev`

**Upstream issue required:** Yes; file from `issue-drafts/fix-chat-auto-scroll-threshold.md` first.

---

## PR Description

### Problem

The chat auto-scroll stops following the bottom when large content arrives. Code blocks
with syntax highlighting, images, and rich markdown can shift `scrollHeight` by several
hundred pixels in a single animation frame. When the user is near the bottom, this pushes
`diff` (distance to bottom) over the rigid 300px threshold in `_smoothScrollStep()`, which
falsely interprets the layout shift as deliberate user scrolling and cancels the scroll.

### Fix

Replace the fixed 300px limit with a viewport-scaled adaptive threshold:

```javascript
// Before
if (diff > 300) {
  _scrollRafId = null;
  return;
}

// After
const viewportHeight = box.clientHeight;
const maxAllowedDiff = Math.max(300, viewportHeight * 1.5);
if (diff > maxAllowedDiff) {
  _scrollRafId = null;
  return;
}
```

`Math.max(300, viewportHeight * 1.5)` retains the 300px minimum so the guard still fires
on small viewports and for genuine user scrolling. For typical desktop viewports (700-900px
tall) the threshold becomes 1050-1350px, which tolerates any realistic content-driven layout
shift while still suppressing auto-scroll when the user has genuinely scrolled far up.

### Testing

**Setup:** Start the app, open a chat session.

1. **Large code block:** Send a message that produces a long code block response. Verify the
   chat auto-scrolls to the bottom and the code block is fully visible without manual
   scrolling.

2. **Image in response:** Trigger a response that includes an embedded image. Verify
   auto-scroll follows to the bottom after the image loads.

3. **User-initiated scroll preserved:** During a response, scroll up by 2-3 viewport-heights.
   Verify auto-scroll does NOT resume dragging you back to the bottom (the guard still fires
   when the user has genuinely scrolled up significantly).

4. **Small viewport:** Resize the browser to a small viewport (< 400px tall). Verify the
   300px minimum floor keeps the guard active: a 400px layout shift on a 300px viewport
   should still suppress auto-scroll.

---

## Filing Notes

- File the upstream issue first (from `issue-drafts/fix-chat-auto-scroll-threshold.md`)
- Get the upstream issue number; fill it into `Fixes #` in the commit message before the PR
  is opened (`git commit --amend` on `fix/chat-auto-scroll-threshold`, then force-push)
- This PR has no dependencies and can be filed independently
