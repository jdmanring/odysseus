# PR Draft: refactor/assets-move → pewdiepie-archdaemon/odysseus:dev

**Branch:** `jdmanring/odysseus:refactor/assets-move`
**Issue:** [#19](https://github.com/jdmanring/odysseus/issues/19) (fork tracking)
**Status:** Ready to file

---

## Title

`refactor: move media assets from docs/ to assets/`

---

## Description

### Problem

Demo media files (screenshots, GIFs, WebM videos) were stored under `docs/`,
which mixes documentation prose with binary assets. This makes it harder to
maintain the docs directory and adds noise to documentation diffs.

### Change

Move all media assets to a top-level `assets/` directory and update
`README.md` and `.gitignore` accordingly.

```
docs/odysseus.jpg  →  assets/landingpage.jpg  (renamed to avoid confusion with icon)
docs/odysseus.svg  →  assets/odysseus.svg
docs/chat.gif      →  assets/chat.gif
docs/bg.webm       →  assets/bg.webm
... (all demo media)
```

The `odysseus.jpg` → `landingpage.jpg` rename prevents the file from being confused
with the application icon (`odysseus.svg` / `odysseus.jpg` in the Qt taskbar).

### Files Changed

- `assets/` (new directory — 17 media files moved here)
- `README.md` (updated image/video references)
- `.gitignore` (updated paths)

### Notes

No functional changes. Pure file reorganization.

### How to Test

1. After merging, open `README.md` — verify all images render correctly (no broken image placeholders).
2. Verify the `assets/` directory exists at repo root and contains the moved media files.
3. Verify `docs/` no longer contains the media files (`odysseus.jpg`, `chat.gif`, `bg.webm`, etc.).
4. Run `grep -r "docs/odysseus\|docs/chat\|docs/bg" README.md` — should return nothing (all references updated).
5. No screenshots required — no visual change.

---

## Filing Notes

This is a standalone refactor with no dependencies. Can be filed in any order.
