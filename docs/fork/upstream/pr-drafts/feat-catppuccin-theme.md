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
### What gap Catppuccin fills in the existing theme set

Odysseus ships 16 built-in themes. The dark and medium-dark themes, compared using their
actual HSL values, fall into distinct hue families:

| Theme | Background | Foreground | Accent hue |
|-------|-----------|-----------|------------|
| `dark` | H220 S13% L18% | H194 S77% L78% (cyan) | H355 (red) |
| `midnight` | H216 S28% L7% | H210 S17% L82% (near-white, barely blue) | H3 (red) |
| `gpt` | H0 S0% L13% | H0 S0% L93% (pure grey) | H0 (grey) |
| `claude` | H60 S3% L15% | H48 S20% L95% (warm white) | H15 (orange) |
| `retrowave` | H240 S28% L14% | H350 S79% L59% (hot pink) | H350 (hot pink) |
| `cyberpunk` | H240 S20% L5% | H183 S98% L52% (electric cyan) | H291 S96% (neon magenta) |
| `ume` | H291 S26% L14% | H316 S72% L86% (bright pink) | H337 (pink) |
| `organs` | H340 S43% L3% | H38 S55% L86% (cream) | H354 (red) |
| `ocean` | H213 S60% L11% | H197 S100% L70% (electric blue) | H208 (blue) |
| `catppuccin` | H240 S21% L15% | **H226 S64% L88% (lavender-white)** | **H258 S54% (mauve)** |

The foreground column shows the gap: every dark theme in the blue-family background
group (dark, midnight, retrowave, cyberpunk, ocean) uses either a fully desaturated
near-white (midnight, S17%), an electric/highly-saturated hue (dark S77% cyan, ocean
S100% blue, cyberpunk S98% electric-cyan), or a contrasting non-blue color (retrowave
hot-pink). None uses a **blue-purple tinted white at moderate saturation** — Catppuccin's
H226/S64%/L88% is a specific perceptual position not occupied by any existing theme.

The accent column shows the same gap: the only purple/violet accent in the dark themes
is cyberpunk's H291/S96% neon magenta. Catppuccin's H258/S54% mauve is a soft purple —
the same hue family, 42 percentage points lower saturation — which behaves completely
differently in practice (readable alongside text, not attention-grabbing neon).

This is the niche Catppuccin's [documented design
philosophy](https://github.com/catppuccin/catppuccin) explicitly targets: "not too dull,
not too bright" — colourful enough to carry distinct hues in the foreground and accent
without reaching electric saturation levels. None of the 16 existing themes occupies
this specific combination of blue-family background, lavender-tinted foreground, and
soft-purple accent.

### Adoption scale confirms the niche is real

456 official ports ([catppuccin.com/ports](https://catppuccin.com/ports/)) spanning 40+
code editors and IDEs, 50+ developer tools, 30+ terminal emulators, and 20+ browsers
([github.com/catppuccin/catppuccin](https://github.com/catppuccin/catppuccin)).
VS Code alone: [1.27M installs](https://marketplace.visualstudio.com/items?itemName=Catppuccin.catppuccin-vsc).
The palette is versioned at [v1.1.0](https://github.com/catppuccin/palette) and
mathematically defined — 26 named colors per flavor — so the colors in this PR will
not change without a clearly communicated major version bump.

### Addressing the ROADMAP note and prior PR closures

The ROADMAP contains the entry: *"I prob shouldnt add more themes."* Both prior
Catppuccin PRs ([#2814](https://github.com/pewdiepie-archdaemon/odysseus/pull/2814),
[#3687](https://github.com/pewdiepie-archdaemon/odysseus/pull/3687)) were closed for
this reason, not for implementation problems — the maintainer noted "the palette is
cleanly done" and "no issue with the implementation itself."

The maintainer's own language is worth noting: "I prob shouldnt" (hedged, not absolute)
and "if themes come back into scope later this can be revisited." Issue
[#3692](https://github.com/pewdiepie-archdaemon/odysseus/issues/3692), opened June 2026
and labeled "Ready for review," is the most recent signal from the project — indicating
the maintainer has since reopened consideration.

This PR makes the minimum possible ask: one entry in the `THEMES` object, no new files,
no maintenance obligation. The design argument above distinguishes this from a generic
"another theme" addition: the existing set has a measurable gap in the blue-purple
moderate-saturation niche that Catppuccin specifically occupies.

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
- **Prior PRs:** #2814 (Wontfix) and #3687 (abandoned) were both closed with the same reason: ROADMAP note "I prob shouldnt add more themes." Neither was closed for implementation quality — vdmkenny said "the palette is cleanly done" (#2814) and "no issue with the implementation itself" (#3687). Reference these in the PR description to show awareness, and note that issue #3692 (labeled "Ready for review", June 2026) represents the maintainer's subsequent re-opening of the question.
- Screenshots required — capture before filing (see How to Test above).

## Visual / UI changes — REQUIRED if you touched anything that renders

- [x] Screenshot or short clip of the change in the running app, attached below. Mobile screenshot too if the change affects mobile layout.
- [x] Style match: the change uses Odysseus's existing visual language (existing CSS variables, button/card classes, no Unicode emoji, Fira Code font, dark-mode-first).
- [x] No new component patterns — extended an existing widget rather than adding a parallel one.
- [ ] **I am not an LLM agent submitting a bulk PR.** I reviewed and tested this change personally before submitting.

### Screenshots / clips

<!-- Attach screenshots by dragging and dropping into this text box. -->
