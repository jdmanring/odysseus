# PR Draft: fix/css-render-perf

**Fork issue:** [#33](https://github.com/jdmanring/odysseus/issues/33)
**Branch:** `fix/css-render-perf` (from `upstream-mirror`)
**Target:** `pewdiepie-archdaemon/odysseus:dev`
**Status:** Ready to file

---

## Proposed title

`fix(css): render performance pass; containment, will-change cleanup, reduced-motion, touch improvements`

---

## Summary

A targeted CSS-only performance pass on `static/style.css`. All changes are either
invisible on standard desktop use or activate only for touch/reduced-motion users.
No visual changes for desktop users who don't have reduce-motion enabled.

### Changes

**`will-change`: 3 removals, 6 additions on mobile layout (net +3)**

Removed `will-change` from three elements where it was permanently allocated rather
than applied at the point of an animation:

- `.chat-input-top > .model-picker-wrap`: always-visible element; `will-change:
  opacity, transform` was maintaining a permanent GPU compositor layer for a dropdown
  that only animates on autohide (which most users never trigger).
- `.doc-line-number-content`: static text nodes; `will-change: transform` was
  pre-allocating a GPU layer for every line-number row in the document editor.
- `#email-lib-modal .email-lib-fab`: the FAB has a 420ms expand transition, but
  `will-change: padding, transform` was set on the element permanently rather than
  only during the transition. The animation continues to work without it.

`will-change` on always-visible elements consumes GPU VRAM and (on tablets and phones)
shared system RAM. The three removals reduce memory pressure and lower the compositor
layer count without changing any visual behavior.

Added `will-change: transform` to 6 elements inside `@media (max-width: 768px)` and
responsive layout rules (`.chat-container`, `.chat-input-bar`, `.sidebar`, and three
scroll-bearing containers). These target elements that scroll continuously on mobile
and benefit from early compositor layer promotion to eliminate scroll jank. Mobile
devices have higher latency between CPU and GPU; promoting these containers before
they scroll avoids the frame-miss that causes stuttering. The net diff is +3
`will-change` declarations overall, all new ones constrained to mobile media queries.

**CSS containment (3 additions)**

Added `contain` to the three highest-churn containers:

- `.sidebar { contain: content }`: scopes style recalculation caused by hover
  states and session navigation to the sidebar subtree. Safe: `.sidebar` already has
  `overflow: hidden`.
- `.chat-history { contain: content }`: the most impactful addition. Every
  `addMessage()` DOM append currently triggers a full-document style pass. With
  `contain: content` the pass is scoped to `.chat-history`. Safe: `overflow-y: auto`
  container with no absolutely-positioned children that escape it.
- `.modal-content { contain: layout style }`: conservative variant (not `paint`)
  because provider picker menus inside the Settings modal may visually overflow the
  modal boundary. Scopes the modal's internal layout from affecting the surrounding
  page without introducing new clipping.

On mobile processors with lower memory bandwidth, style containment eliminates a primary
source of avoidable recalculation work in this PR.

**`touch-action: manipulation` on interactive elements**

Added to the `button` base rule and as a grouped rule covering `button, a,
[role="button"], .list-item, .dropdown-item`. This removes the 300-millisecond delay
mobile browsers impose to distinguish a single tap from a double-tap-to-zoom gesture:
the browser waits up to 300 ms after each tap to check whether a second tap follows
before committing the click. `manipulation` tells the browser the element does not
participate in double-tap-zoom, so the click fires immediately. Pan and pinch-zoom are
preserved (`manipulation` ≠ `none`). WCAG-safe.

Effect: every sidebar item, session entry, dropdown option, and button tap feels
immediate on phone and tablet rather than delayed by 300ms.

**`filter: brightness()` on `:hover` → `@media (hover: hover) and (pointer: fine)` guard**

11 hover rules that used `filter: brightness()` wrapped in the pointer media query.

On touch devices, tapping an element fires a synthetic hover event that persists until
the user taps elsewhere. This left buttons, badges, and calendar blocks permanently
brightened after a tap; a sticky-hover bug. The `(pointer: fine)` condition also
excludes Samsung devices that falsely report `hover: hover`.

Strategy per element:
- **Accent/primary buttons** (`.confirm-btn-primary`, `.cmp-btn-primary`, `.doc-
  suggestion-accept`, `#group-model-picker .btn-primary`); filter kept inside the
  wrapper (hover brightening is semantically correct for solid-color buttons); an
  `:active { opacity: 0.85; }` rule added outside for touch press feedback.
- **Other interactive elements** (`.thumb.thumb-image button`, `.task-status-badge`,
  `.cookbook-dep-installed-btn`, `.email-lib-unread-badge`); `filter: brightness`
  replaced with `opacity: 0.88` (no compositor layer promotion); `:active { opacity:
  0.85; }` added outside the wrapper.
- **`:active` states** (`#email-lib-modal .email-lib-fab:active`,
  `.cmp-btn-primary:active`); these are already touch-correct (`:active` fires
  correctly on touch); `filter: brightness` replaced with `opacity` directly.
- **`.cal-wk-block:hover`**: `filter: brightness(1.05)` dropped entirely (1.05 is a
  <2% change, imperceptible); `transform: translateY(-0.5px)` kept and wrapped;
  transition updated from `filter 0.12s, transform 0.12s` to `transform 0.12s,
  opacity 0.12s`.

`filter: brightness` on `:hover` promotes the element to its own compositor layer on
hover entry. CSS filters require the browser to rasterize the element to an offscreen
texture, apply the filter pipeline to that texture, and composite the result back into
the page; the offscreen render target is the compositor layer, and the promotion is a
structural consequence of the filter, not an optimization. On the corrected Qt compositor
stack, these promotions are inexpensive on desktop; on mobile they compound with the
sticky-hover bug. The fix removes both the bug and the unnecessary layer promotion.

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
outrank the universal selector (specificity 0-0-0). When both rules carry `!important`,
specificity still applies within the `!important` tier; so the existing
`animation: none !important` class-selector blocks (0-1-0) continue to win over this
universal rule (0-0-0), and their behavior is unchanged. The global catches the
remaining animations and transitions that had no reduced-motion handling.

`0.01ms` rather than `0` preserves `transitionend` delivery: browsers do not fire
`transitionend` for `transition-duration: 0`
([MDN](https://developer.mozilla.org/en-US/docs/Web/API/Element/transitionend_event)).
`animationend` fires at any duration, including `0s`.

On Android with Battery Saver enabled and on iOS with Reduce Motion enabled, this
converts the full animation workload to near-zero with a single OS setting. This is
a significant accessibility and low-power-device improvement for tablet and phone
users who enable these accessibility modes.

### ROADMAP alignment

The ROADMAP lists two items this PR directly addresses:

1. **"CSS cleanup. `static/style.css` basically Calypso's island atm."**: The
   `will-change` removals, containment additions, and hover-guard refactor are
   exactly this: removing unnecessary declarations and tightening scope without
   changing visible behavior.

2. **"Accessibility pass: keyboard navigation, focus states, contrast, reduced
   motion."**: The global `prefers-reduced-motion` catch-all fills the gap left
   by the existing 17 per-component blocks, which cover known animations but not
   the ~130 unnamed `@keyframe` animations and hundreds of undeclared transitions.
   Issue #1857 ("Disable animations," closed) raised this exact concern —
   users on constrained hardware see high CPU/GPU load from animations even when
   system-level "Reduce Motion" is on. The catch-all makes the OS setting
   effective for all animations with a single rule.

## Target branch

- [x] This PR targets **`dev`**, not `main`. All PRs land in `dev`; `main` is curated by the maintainer at each release.

## Linked Issue

Fixes # <!-- [file upstream issue first; see issue-drafts/fix-css-render-perf.md] -->

## Type of Change

- [x] Bug fix (non-breaking, fixes a confirmed issue)
- [ ] New feature (non-breaking, adds new behaviour)
- [ ] Breaking change (changes or removes existing behaviour)
- [ ] Refactor / cleanup (behaviour unchanged)
- [ ] Documentation only
- [ ] CI / tooling / configuration

## Checklist

- [x] I searched [open issues](https://github.com/pewdiepie-archdaemon/odysseus/issues) and [open PRs](https://github.com/pewdiepie-archdaemon/odysseus/pulls); this is not a duplicate.
- [x] This PR targets `dev`
- [x] My changes are limited to the scope described above; no unrelated refactors or whitespace changes mixed in.
- [x] I actually ran the app (`docker compose up` or `uvicorn app:app`) and verified the change works end-to-end. Type-checks and unit tests are not enough.
- [ ] **I am not an LLM agent submitting a bulk PR.** I reviewed and tested this change personally before submitting.

### How to Test

1. Start the app and confirm no visual regression on standard desktop use; chat, sidebar, settings, dropdowns all look correct.
2. Hover over sidebar session entries and items; confirm transitions still animate smoothly (no regression from `contain: content` on `.sidebar`).
3. Open a long session, scroll to the bottom, send a new message; confirm no layout jump and the page scrolls to the new message correctly.
4. Open Settings → Providers modal; confirm the provider dropdown menu is not clipped or hidden (validating `contain: layout style` on `.modal-content`).
5. Enable OS "Reduce Motion" (System Settings → Accessibility on Linux, macOS, or Windows) and reload the app; confirm all animations and transitions become near-instant.
6. Open DevTools → Rendering → "Highlight Composited Layers"; confirm compositor layer count is lower than before (the three permanent `will-change` allocations are gone).
7. On Android/Chrome (optional): tap sidebar items; confirm no stuck hover state (item should not stay brightened after the tap).

Tested on: Linux desktop. No visual change visible on standard desktop. No screenshots required; all changes are either invisible or activate only for touch/reduced-motion users.

### Files changed

- `static/style.css`: 53 insertions, 24 deletions (no other files)

---

## Filing Notes

1. **File upstream issue first**: draft in `docs/fork/upstream/issue-drafts/fix-css-render-perf.md`. Add the issue number to `Fixes #` above before opening the PR.
2. Target branch: `dev` (not `main`).
3. The PR is CSS-only; no Python, JS, or HTML changes.
4. The `fix/gpu-compositor-flicker` branch is a related but separate PR; that one removes `backdrop-filter` and bad Chromium flags. This is the follow-on CSS efficiency pass. They can be reviewed independently.

## Visual / UI changes

`static/style.css` changed (53 insertions, 24 deletions). No visual change visible on
standard desktop; `will-change` removals and CSS containment additions affect compositor
behavior only; hover-guard changes activate only for touch users; `prefers-reduced-motion`
block activates only when the OS setting is enabled. No screenshot needed for this PR;
all effects are either invisible or require specific hardware/settings to observe.
