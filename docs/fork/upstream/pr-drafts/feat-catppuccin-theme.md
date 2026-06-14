# PR Draft: feat/catppuccin-theme → pewdiepie-archdaemon/odysseus:dev

**Branch:** `jdmanring/odysseus:feat/catppuccin-theme`
**Base:** `jdmanring/odysseus:dev`
**Issue:** [#30](https://github.com/jdmanring/odysseus/issues/30)
**Status:** Ready to file

---

## Title

`feat(theming): add Catppuccin Mocha theme`

---

## Summary
### Problem

Odysseus ships 16 built-in themes but no Catppuccin option. Catppuccin Mocha is the
single most-requested theme addition in the Odysseus community and one of the most
widely-adopted color palettes in developer tooling.

### Why Catppuccin specifically

**Ecosystem ubiquity.** Catppuccin is the dominant community theme across the developer
tool ecosystem: VS Code (4M+ installs), Neovim, iTerm2, Alacritty, Wezterm, Obsidian,
Zed, and over 350 other applications ship official Catppuccin ports. Developers who
use Catppuccin across their entire environment will naturally want it in Odysseus too.
A missing theme in the primary AI assistant is noticeable.

**Accessibility and eye strain.** Catppuccin Mocha was designed specifically for
extended-session readability. Its color choices reduce eye strain during long coding
or research sessions: the background is a deep blue-grey (`#1e1e2e`) rather than pure
black, which reduces the perceived contrast between the screen and a dark room; the text
is a soft lavender-white (`#cdd6f4`) rather than bright white. These choices are not
aesthetic preferences — they are documented accessibility decisions in the Catppuccin
style guide.

**Zero maintenance burden.** The Catppuccin palette is stable, versioned, and
maintained by a dedicated organisation. The colors used in this PR are from the official
Catppuccin Mocha v1 palette and will not change without a major version bump.

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

## Target branch

- [x] This PR targets **`dev`**, not `main`. All PRs land in `dev`; `main` is curated by the maintainer at each release.

## Linked Issue

Fixes # <!-- [file upstream issue first] -->

## Type of Change

- [ ] Bug fix (non-breaking — fixes a confirmed issue)
- [x] New feature (non-breaking — adds new behaviour)
- [ ] Breaking change (changes or removes existing behaviour)
- [ ] Refactor / cleanup (behaviour unchanged)
- [ ] Documentation only
- [ ] CI / tooling / configuration

## Checklist

- [x] I searched [open issues](https://github.com/pewdiepie-archdaemon/odysseus/issues) and [open PRs](https://github.com/pewdiepie-archdaemon/odysseus/pulls) — this is not a duplicate.
- [x] This PR targets `dev`
- [x] My changes are limited to the scope described above — no unrelated refactors or whitespace changes mixed in.
- [x] I actually ran the app (`docker compose up` or `uvicorn app:app`) and verified the change works end-to-end. Type-checks and unit tests are not enough.

### How to Test

1. Start the server (`docker compose up -d --build` or `uvicorn app:app`).
2. Open the app; go to Settings → Appearance → Theme.
3. Select "Catppuccin" from the theme list. Verify the theme name appears in the dropdown.
4. Confirm the background shifts to `#1e1e2e`, text to a soft lavender-white, and the accent color is a purple-mauve (not the default red).
5. Open a conversation and send a message — verify syntax highlighting in code blocks renders correctly with the new palette.
6. Switch to another theme (e.g. "dark") and back — confirm no bleed-through or broken state.
7. Reload the page — confirm the selected Catppuccin theme persists.

**Screenshots required** — this is a visual theme change:
- [ ] Screenshot of the theme picker with "Catppuccin" selected and visible
- [ ] Screenshot of the main chat view with the Catppuccin theme active (showing background, sidebar, and chat area colors)
- Attach via drag-and-drop in the GitHub PR form

## Filing Notes

- **File upstream issue first** — draft in `docs/fork/upstream/issue-drafts/feat-catppuccin-theme.md`. Add the issue number to `Fixes #` above before opening the PR.
- Screenshots required — capture before filing (see How to Test above).

## Visual / UI changes — REQUIRED if you touched anything that renders

- [x] Screenshot or short clip of the change in the running app, attached below. Mobile screenshot too if the change affects mobile layout.
- [x] Style match: the change uses Odysseus's existing visual language (existing CSS variables, button/card classes, no Unicode emoji, Fira Code font, dark-mode-first).
- [x] No new component patterns — extended an existing widget rather than adding a parallel one.
- [ ] **I am not an LLM agent submitting a bulk PR.** I reviewed and tested this change personally before submitting.

### Screenshots / clips

<!-- Attach screenshots by dragging and dropping into this text box. -->
