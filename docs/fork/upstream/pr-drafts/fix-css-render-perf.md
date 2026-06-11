# PR Draft: fix/css-render-perf

**Fork issue:** [#33](https://github.com/jdmanring/odysseus/issues/33)
**Branch:** `fix/css-render-perf` (from `upstream-mirror`)
**Target:** `pewdiepie-archdaemon/odysseus:dev`

---

## Proposed title

`fix(css): render performance pass — containment, will-change cleanup, reduced-motion, touch improvements`

---

## PR description (for upstream reviewers)

### Summary

A targeted CSS-only performance pass on `static/style.css`. All changes are either
invisible on standard desktop use or activate only for touch/reduced-motion users.
No visual changes for desktop users who don't have reduce-motion enabled.

### Changes

**`will-change` cleanup (3 removals)**

Removed `will-change` from three elements where it was permanently allocated rather
than applied at the point of an animation:

- `.chat-input-top > .model-picker-wrap` — always-visible element; `will-change:
  opacity, transform` was maintaining a permanent GPU compositor layer for a dropdown
  that only animates on autohide (which most users never trigger).
- `.doc-line-number-content` — static text nodes; `will-change: transform` was
  pre-allocating a GPU layer for every line-number row in the document editor.
- `#email-lib-modal .email-lib-fab` — the FAB has a 420ms expand transition, but
  `will-change: padding, transform` was set on the element permanently rather than
  only during the transition. The animation continues to work without it.

`will-change` on always-visible elements consumes GPU VRAM and (on tablets and phones)
shared system RAM. The three removals reduce memory pressure and lower the compositor
layer count without changing any visual behavior.

**CSS containment (3 additions)**

Added `contain` to the three highest-churn containers:

- `.sidebar { contain: content }` — scopes style recalculation caused by hover
  states and session navigation to the sidebar subtree. Safe: `.sidebar` already has
  `overflow: hidden`.
- `.chat-history { contain: content }` — the most impactful addition. Every
  `addMessage()` DOM append currently triggers a full-document style pass. With
  `contain: content` the pass is scoped to `.chat-history`. Safe: `overflow-y: auto`
  container with no absolutely-positioned children that escape it.
- `.modal-content { contain: layout style }` — conservative variant (not `paint`)
  because provider picker menus inside the Settings modal may visually overflow the
  modal boundary. Scopes the modal's internal layout from affecting the surrounding
  page without introducing new clipping.

On mobile processors with lower memory bandwidth, style containment is the single
largest source of avoidable recalculation work eliminated here.

**`touch-action: manipulation` on interactive elements**

Added to the `button` base rule and as a grouped rule covering `button, a,
[role="button"], .list-item, .dropdown-item`. This removes the 300ms tap-delay that
mobile browsers impose to distinguish single-tap from double-tap-zoom. Pan and
pinch-zoom are preserved (`manipulation` ≠ `none`). WCAG-safe.

Effect: every sidebar item, session entry, dropdown option, and button tap feels
immediate on phone and tablet rather than delayed by 300ms.

**`filter: brightness()` on `:hover` → `@media (hover: hover) and (pointer: fine)` guard**

11 hover rules that used `filter: brightness()` wrapped in the pointer media query.

On touch devices, tapping an element fires a synthetic hover event that persists until
the user taps elsewhere. This left buttons, badges, and calendar blocks permanently
brightened after a tap — a sticky-hover bug. The `(pointer: fine)` condition also
excludes Samsung devices that falsely report `hover: hover`.

Strategy per element:
- **Accent/primary buttons** (`.confirm-btn-primary`, `.cmp-btn-primary`, `.doc-
  suggestion-accept`, `#group-model-picker .btn-primary`) — filter kept inside the
  wrapper (hover brightening is semantically correct for solid-color buttons); an
  `:active { opacity: 0.85; }` rule added outside for touch press feedback.
- **Other interactive elements** (`.thumb.thumb-image button`, `.task-status-badge`,
  `.cookbook-dep-installed-btn`, `.email-lib-unread-badge`) — `filter: brightness`
  replaced with `opacity: 0.88` (no compositor layer promotion); `:active { opacity:
  0.85; }` added outside the wrapper.
- **`:active` states** (`#email-lib-modal .email-lib-fab:active`,
  `.cmp-btn-primary:active`) — these are already touch-correct (`:active` fires
  correctly on touch); `filter: brightness` replaced with `opacity` directly.
- **`.cal-wk-block:hover`** — `filter: brightness(1.05)` dropped entirely (1.05 is a
  <2% change, imperceptible); `transform: translateY(-0.5px)` kept and wrapped;
  transition updated from `filter 0.12s, transform 0.12s` to `transform 0.12s,
  opacity 0.12s`.

`filter: brightness` on `:hover` promotes the element to its own compositor layer on
hover entry. On the corrected Qt compositor stack, these layer promotions are
inexpensive on desktop; on mobile they compound with the sticky-hover bug. The fix
removes both the bug and the unnecessary layer promotion.

**Global `prefers-reduced-motion` catch-all**

Appended at the end of the file, after all 17 existing per-component
`prefers-reduced-motion` blocks:

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

The existing per-component rules use class selectors (specificity 0-1-0), which
override the universal selector (specificity 0-0-0) even with `!important` at equal
specificity level — so existing `animation: none !important` blocks continue to apply
correctly. The global catches the ~130 `@keyframe` animations and hundreds of
transitions that had no reduced-motion handling.

`0.01ms` rather than `0` preserves delivery of `animationend` and `transitionend` JS
events (browsers may skip these for `duration: 0`).

On Android with Battery Saver enabled and on iOS with Reduce Motion enabled, this
converts the full animation workload to near-zero with a single OS setting. This is
a significant accessibility and low-power-device improvement for tablet and phone
users who enable these accessibility modes.

### Testing

- Boot app; confirm no visual regression on standard desktop use
- Sidebar hover: transitions intact, no flicker
- Open a long session: scroll to bottom, add a message, confirm no layout jump
- Open Settings, toggle provider dropdown: no clipping or overflow issues
- Enable OS "Reduce Motion": all animations become instant
- On Android/Chrome (if available): tap sidebar items — no stuck hover state after tap
- DevTools Layers panel: compositor layer count lower than before (fewer `will-change`)

### Files changed

- `static/style.css` — 53 insertions, 24 deletions (no other files)

---

## Filing notes

1. No upstream issue needed first — this is a self-contained CSS perf fix, not a
   user-visible bug report. Open the PR directly.
2. Target branch: `dev` (not `main`)
3. The PR is CSS-only; no Python, JS, or HTML changes.
4. The `fix/gpu-compositor-flicker` branch (#32) is a related but separate PR —
   that one removes `backdrop-filter` and bad Chromium flags. This one is the
   follow-on CSS efficiency pass. They can be reviewed independently.
