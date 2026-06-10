# PR Draft: feat/catppuccin-theme → pewdiepie-archdaemon/odysseus:dev

**Branch:** `jdmanring/odysseus:feat/catppuccin-theme`
**Base:** `jdmanring/odysseus:dev`
**Issue:** [#30](https://github.com/jdmanring/odysseus/issues/30)
**Status:** Ready to file

---

## Title

`feat(theming): add Catppuccin Mocha theme`

---

## Description

### Problem

Odysseus ships 16 built-in themes but has no Catppuccin option. Catppuccin is a widely-used, well-designed color palette. The existing themes use various accent colors that don't align with a cohesive design system.

### Solution

Add a `catppuccin` theme using the Catppuccin Mocha palette, with colors chosen to harmonize with Odysseus's existing cyan/blue accent design language:

| Property | Color | Rationale |
|----------|-------|-----------|
| Background | `#1e1e2e` | Mocha base surface |
| Foreground | `#9cdef2` | Matches Odysseus's signature cyan-blue accent |
| Panel | `#181825` | Mocha surface0 |
| Border | `#355a66` | Matches the dark theme's border for visual consistency |
| Accent/Red | `#e06c75` | Matches the default dark theme's red for continuity |

The default theme remains `dark` — catppuccin is an opt-in choice for users who prefer it.

### Files Changed

- `static/js/theme.js` — added `catppuccin` entry to `THEMES` export

### Notes

- Single-line addition — no default theme change, no breaking changes
- Colors derived from the official Catppuccin Mocha palette, tuned to match Odysseus's design system
- Compatible with the existing custom theme engine (custom themes can reference or extend it)
- No changes to theme scheduling, persistence, or UI

### Testing

- [ ] Verify theme appears in theme dropdown/popup
- [ ] Verify colors render correctly (background, foreground, panels, borders, accent)
- [ ] Verify other themes remain unaffected
