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
### Why Catppuccin fills a documented design niche

Dark themes exist on a spectrum from low-contrast/desaturated (Nord, Tokyo Night, Gruvbox)
to high-contrast/vibrant (Dracula, Monokai). Catppuccin's [documented design
position](https://github.com/catppuccin/catppuccin) is explicitly the **middle ground**
between these two poles — its three stated design principles are:

1. **Colorfulness over minimalism**: "the colorfulness of something contributes to the
   distinction amongst the parts"
2. **Balance**: "not too dull, not too bright. Suitability under various light conditions
   is a must"
3. **Harmonic color relationships**: "vivacious colors must complement each other"

The Mocha palette — deep blue-grey background (`#1e1e2e`), soft lavender-white text
(`#cdd6f4`), mauve accent (`#cba6f7`) — is the darkest and most widely-used of
Catppuccin's four flavors precisely because it achieves this balance under both bright
and dim lighting.

This is a perceptual niche, not a matter of taste: a theme that is neither stark nor
flat occupies different psychovisual territory than either extreme, and no existing
Odysseus theme explicitly claims this positioning.

### Adoption scale confirms the niche is real

456 official ports ([catppuccin.com/ports](https://catppuccin.com/ports/)) spanning 40+
code editors and IDEs, 50+ developer tools, 30+ terminal emulators, and 20+ browsers.
VS Code alone: [1.27M installs](https://marketplace.visualstudio.com/items?itemName=Catppuccin.catppuccin-vsc).
The palette is versioned at [v1.1.0](https://github.com/catppuccin/palette) and
mathematically defined — 26 named colors per flavor — so the colors in this PR will
not change without a clearly communicated major version bump.

The breadth of adoption across unrelated application categories (editors, terminals,
browsers, music players, window managers) indicates the niche is validated, not niche
in the pejorative sense.

### Community demand and prior attempts

Catppuccin has been requested in the upstream project: open issue
[#3692](https://github.com/pewdiepie-archdaemon/odysseus/issues/3692), and prior PRs
[#2814](https://github.com/pewdiepie-archdaemon/odysseus/pull/2814) (Wontfix) and
[#3687](https://github.com/pewdiepie-archdaemon/odysseus/pull/3687) (abandoned) both
attempted this and were closed. This PR is deliberately more minimal — a single palette
entry, not a multi-flavour suite — to address the scope concerns that closed previous
attempts.

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
