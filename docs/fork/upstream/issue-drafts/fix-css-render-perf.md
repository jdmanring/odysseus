# Upstream Issue Draft: fix-css-render-perf

**File on:** `odysseus-dev/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/fix-css-render-perf.md`
**Branch:** `fix/css-render-perf`
**Type:** Bug / Performance

---

## Title

`[CSS] Unnecessary GPU memory usage and style recalculation — will-change on always-visible elements, no CSS containment, sticky hover on touch`

---

## Body

**Install method:** Docker / manual Python / native

**OS / device:** All platforms; most impactful on mobile/tablet and on NVIDIA + Wayland

**Browser (if applicable):** Any Chromium-based renderer (including QtWebEngine)

**Steps to Reproduce:**
1. Open the app in Chrome DevTools with Rendering → "Highlight Composited Layers" enabled.
2. Observe the compositor layer count without interacting.
3. Open a long chat session and send a new message.
4. On a touch device (or browser DevTools touch simulation): tap a sidebar item or button.

**Expected:**
- Only elements currently animating should hold compositor layers.
- New messages appending to chat history should not trigger a full-document style recalculation.
- Touch-tapped elements should not remain in a hover-brightened state after the tap.

**Actual:**
- Three always-visible elements hold permanent GPU compositor layers due to `will-change` declarations: `.chat-input-top > .model-picker-wrap` (`will-change: opacity, transform`), `.doc-line-number-content` (`will-change: transform` on every line-number row), and `#email-lib-modal .email-lib-fab` (`will-change: padding, transform`). These allocate GPU VRAM/RAM even when not animating.
- Every `addMessage()` call triggers a full-document style recalculation because `.chat-history` has no CSS containment.
- On touch devices, 11 `filter: brightness()` hover rules fire on tap and persist (sticky hover), leaving buttons, badges, and calendar blocks permanently brightened after a tap.
- Users with OS-level "Reduce Motion" enabled are not covered by the existing per-component rules for the ~130 `@keyframe` animations and hundreds of transitions that have no reduced-motion handling.

**Logs / Error Output:**
No error logged — symptoms are visible in DevTools (compositor layer count, style recalculation in Performance timeline) and as stuck hover states on touch.

**Additional context:** This is a CSS-only fix with no visual change for standard desktop use:

- Remove `will-change` from the three permanently-allocated elements — the animations on these elements continue to work without pre-allocation.
- Add `contain: content` to `.sidebar` and `.chat-history`, and `contain: layout style` to `.modal-content` — scopes style recalculation to subtrees rather than triggering document-wide passes.
- Add `touch-action: manipulation` to interactive elements — removes the 300 ms tap delay on mobile without affecting pan/pinch-zoom.
- Wrap 11 `filter: brightness()` hover rules in `@media (hover: hover) and (pointer: fine)` — prevents sticky-hover on touch; adds `:active` states for touch press feedback instead.
- Add a global `prefers-reduced-motion` catch-all after the existing per-component blocks — covers all animations and transitions not already handled.

Related: #1857 ("Disable animations," closed) raised the animation CPU/GPU load concern for low-power hardware — users report fans spinning and heat from Odysseus animations even with OS "Reduce Motion" on. The per-component `prefers-reduced-motion` blocks in the existing CSS cover some animations but leave the majority unhandled; the catch-all makes the OS setting effective universally.
