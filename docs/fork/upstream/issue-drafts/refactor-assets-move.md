# Upstream Issue Draft: refactor-assets-move

**File on:** `pewdiepie-archdaemon/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/refactor-assets-move.md`
**Branch:** `refactor/assets-move`
**Type:** Refactor / Cleanup

---

## Title

`[Repo] Move demo media to assets/, application icon to static/icons/ — separate binary files from documentation prose`

---

## Body

**Area:** Repository structure

**Problem / Motivation:**
Demo media files (screenshots, GIFs, WebM videos used in `README.md`) are stored under `docs/`. This mixes binary assets with documentation prose, which has two practical effects:
1. Documentation PRs and diffs include binary media files, making them harder to review.
2. `docs/odysseus.jpg` shares a base name with the application icon (`odysseus.svg`), creating a naming ambiguity for contributors navigating the repository.

**Proposed Solution:**
Move all demo media files to a top-level `assets/` directory. Move the application icon SVG to `static/icons/` where the PWA manifest icons already live. Update `README.md`, `manifest.json`, `.gitignore`, and build script references accordingly.

```
docs/odysseus.jpg  →  assets/landingpage.jpg  (renamed to remove icon ambiguity)
docs/odysseus.svg  →  static/icons/odysseus.svg  (co-located with PWA icons)
docs/chat.gif      →  assets/chat.gif
docs/bg.webm       →  assets/bg.webm
[all remaining demo media in docs/]
```

`odysseus.jpg` is renamed to `landingpage.jpg` to prevent it from being confused with the application icon. The SVG goes to `static/icons/` rather than `assets/` because it is an application icon, not a README screenshot — it belongs alongside the 192px and 512px PNG manifest icons that already live there, and can be referenced directly in `manifest.json` as `"sizes": "any"` for browsers that support SVG icons.

No functional changes to the app. Pure file reorganization — 17 files moved, references updated.

**Alternatives Considered:**
- All icons in `assets/`: `assets/` is the right home for README media, but not for web-served app icons. The XDG desktop entries and PWA manifest both reference icon files; co-locating them in `static/icons/` is cleaner.
- Leave as-is: current state — binary files mixed into `docs/` alongside prose.
