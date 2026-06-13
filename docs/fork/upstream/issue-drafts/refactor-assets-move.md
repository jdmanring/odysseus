# Upstream Issue Draft: refactor-assets-move

**File on:** `pewdiepie-archdaemon/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/refactor-assets-move.md`
**Branch:** `refactor/assets-move`
**Type:** Refactor / Cleanup

---

## Title

`[Repo] Move demo media assets from docs/ to assets/ — separate binary files from documentation prose`

---

## Body

**Area:** Repository structure

**Problem / Motivation:**
Demo media files (screenshots, GIFs, WebM videos used in `README.md`) are stored under `docs/`. This mixes binary assets with documentation prose, which has two practical effects:
1. Documentation PRs and diffs include binary media files, making them harder to review.
2. `docs/odysseus.jpg` shares a base name with the application icon (`odysseus.svg`), creating a naming ambiguity for contributors navigating the repository.

**Proposed Solution:**
Move all demo media files to a new top-level `assets/` directory and update `README.md` and `.gitignore` references accordingly:

```
docs/odysseus.jpg  →  assets/landingpage.jpg  (renamed to remove icon ambiguity)
docs/odysseus.svg  →  assets/odysseus.svg
docs/chat.gif      →  assets/chat.gif
docs/bg.webm       →  assets/bg.webm
[all remaining demo media in docs/]
```

`odysseus.jpg` is renamed to `landingpage.jpg` to prevent it from being confused with the application icon (`odysseus.svg` / `odysseus.jpg`).

No functional changes. Pure file reorganization — 17 files moved, `README.md` references updated.

**Alternatives Considered:**
- `static/` or `media/`: `assets/` is the most conventional name for this purpose in open-source projects and is already used by similar projects.
- Leave as-is: current state — binary files mixed into `docs/` alongside prose.
