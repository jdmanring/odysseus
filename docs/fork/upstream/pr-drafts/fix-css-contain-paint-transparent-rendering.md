# PR Draft: fix/css-contain-paint-transparent-rendering -> odysseus-dev/odysseus:dev

> **Note before filing (2026-08-03).** `develop` has since moved PAST this
> branch's `.sidebar` half. A deliberate iteration on 2026-06-24 (`e9e5010d`)
> removed `contain` from `.sidebar` entirely and added `background: var(--bg)` to
> `chat-container` instead; `.chat-history` kept `contain: layout style`
> (`3f15dbb8`). So develop is not missing this work, it superseded half of it,
> and this branch's test fails there by design.
>
> Upstream never had `contain` on `.sidebar` at all, so the `.sidebar` half of
> this PR is a *narrowing that upstream does not need*. Consider filing only the
> `.chat-history` half, or re-cutting the branch against develop's final state.


**Branch:** `fix/css-contain-paint-transparent-rendering`
**Status:** Ready to file
**Base:** cut from `upstream-mirror`, 2 files, +91

---

## Title

`fix(css): use contain: layout style on sidebar and chat-history`

---

## Summary

### Problem

`contain: content` implies `contain: paint`, and paint containment breaks two
rendering paths that both depend on the element **not** being isolated:

**1. Frosted sidebar.** `.sidebar` + `body.theme-frosted`'s `backdrop-filter`.
Paint containment composites the sidebar into its own GPU layer, so
`backdrop-filter` samples *that layer* - which is empty - instead of the
composited scene behind the sidebar. The blur silently fails or renders wrong.

**2. Transparent chat area.** `.chat-history` is transparent with
`overflow-y: auto`, and paint containment promotes the scroll container to its
own compositor layer. Under Qt WebEngine with a small tile budget, evicted tiles
in that layer render as **solid colour** rather than passing through to the
canvas/body background, hiding the animated background behind the chat.

Both are pure rendering faults with no error and no console output, which is why
they read as theme bugs rather than a containment side effect.

### Fix

Use `contain: layout style` on both elements.

This keeps the reason containment was added - style-recalculation scoping - while
dropping the paint isolation and the independent compositor layer that cause the
two faults. It is a narrowing, not a removal.

**This already has precedent in the codebase.** `.modal-content` uses
`contain: layout style` for exactly this reason: paint containment there clipped
overflowing provider-picker menus. Same trade, same conclusion, now applied to
the two elements that need it.

---

## Verification

**4 passed**, measured 2026-08-03. The tests assert the containment value on both
selectors, so a future `contain: content` reintroducing the fault fails here.

Both faults were confirmed visually before and after on the affected build; the
sidebar blur and the animated background return.

---

## Scope

`static/style.css` (2 lines) and one test file.
