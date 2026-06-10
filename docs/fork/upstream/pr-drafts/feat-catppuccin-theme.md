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

Odysseus ships 16 built-in themes but has no Catppuccin option. Catppuccin is a widely-used, well-designed color palette with a strong community following.

### Solution

Add a `catppuccin` theme using the Catppuccin Mocha palette with a mauve accent:

| Property | Color | Rationale |
|----------|-------|-----------|
| Background | `#1e1e2e` | Mocha base surface |
| Foreground | `#cdd6f4` | Mocha text — soft, readable lavender-white |
| Panel | `#181825` | Mocha surface0 |
| Border | `#5b6078` | Mocha overlay0 |
| Accent/Red | `#8565d1` | Mauve — distinctive accent that differentiates from other themes |

The default theme remains `dark` — catppuccin is an opt-in choice.

### Files Changed

- `static/js/theme.js` — added `catppuccin` entry to `THEMES` export

### Notes

- Single-line addition — no default theme change, no breaking changes
- Colors from the official Catppuccin Mocha palette (https://catppuccin.com)
- Compatible with the existing custom theme engine, color picker, and background effects
- No changes to theme scheduling, persistence, or UI

### Testing

- [ ] Verify theme appears in theme dropdown/popup
- [ ] Verify colors render correctly (background, foreground, panels, borders, accent)
- [ ] Verify syntax highlighting derives correctly from the new theme
- [ ] Verify other themes remain unaffected
