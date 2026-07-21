# Upstream Issue Draft: feat-catppuccin-theme

**File on:** `odysseus-dev/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/feat-catppuccin-theme.md`
**Branch:** `feat/catppuccin-theme`
**Type:** Enhancement

---

## Title

`[Theming] Add Catppuccin Mocha theme`

---

## Body

**Area:** Theming / Appearance

**Problem / Motivation:**
Odysseus ships 16 built-in themes but has no Catppuccin option. Catppuccin is one of the most widely-used community color palettes, with official ports across hundreds of applications. Users who prefer the Catppuccin Mocha palette currently have to approximate it manually using the custom color picker, but there is no first-class preset and no way to get the exact official palette values without looking them up separately.

**Proposed Solution:**
Add a `catppuccin` entry to `THEMES` in `static/js/theme.js` using the official Catppuccin Mocha palette with mauve accent:

| Property | Color | Source |
|----------|-------|--------|
| Background | `#1e1e2e` | Mocha Base |
| Foreground | `#cdd6f4` | Mocha Text |
| Panel | `#181825` | Mocha Mantle |
| Border | `#585b70` | Mocha Surface2 |
| Accent | `#cba6f7` | Mocha Mauve |

The default theme remains `dark`. This is an opt-in preset — a single entry added to the existing themes list. No changes to the theme engine, scheduling, persistence, or UI.

**Alternatives Considered:**
The existing custom color picker lets users approximate any palette, but a first-class preset is more discoverable, ensures exact official palette values, and is consistent with how other named themes (rose-pine, gruvbox, etc.) are provided.
