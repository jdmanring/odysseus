# PR Draft: refactor/assets-move → pewdiepie-archdaemon/odysseus:dev

**Branch:** `refactor/assets-move`
**Issue:** [#19](https://github.com/jdmanring/odysseus/issues/19) (fork tracking)
**Status:** Ready to file

---

## Title

`refactor: move demo media to assets/, application icon to static/icons/`

---

## Summary
### Problem

Demo media files (screenshots, GIFs, WebM videos) are stored under `docs/`, mixing
documentation prose with binary assets. This causes several practical problems.

### Why the current layout is harmful

**`docs/` is becoming a documentation directory, and binary media files pollute it.**
Once documentation prose lands in `docs/` — architecture notes, contributor guides,
API references — developers navigating there will encounter 14 GIF, WebM, and JPEG
files at the root. Those files are README embed assets and have nothing to do with
documentation content. This refactor separates them before the documentation tree grows.
A separate PR adding markdown documentation to `docs/ai/`, `docs/dev/`, and `docs/user/`
uses `assets/` paths; either PR can land independently.

**Git history and diff quality.** Binary files in `docs/` appear in every
`git log --stat` and `git diff --stat` that touches documentation. A change to a GIF
produces an uninformative `Binary files ... differ` diff. Any patch that touches
documentation alongside media files generates misleading stats. This is a concrete,
verifiable problem: run `git log --stat -- docs/` on the current repo and observe that
binary file churn appears in a directory that should contain only documentation diffs.

**`docs/odysseus.jpg` is a self-describing name problem.** In an `assets/` directory,
`odysseus.jpg` reads as a project logo or icon. It is actually a landing page screenshot.
Renaming to `landingpage.jpg` makes the file's purpose clear without inspecting the content.

### Change

Move all 14 demo media files to a top-level `assets/` directory. Move the application
icon SVG to `static/icons/` where the PWA manifest icons already live. Update `README.md`,
`manifest.json`, `.gitignore`, and build script references accordingly.

```
docs/odysseus.jpg          →  assets/landingpage.jpg          (renamed; see above)
docs/odysseus-wordmark.png →  assets/odysseus-wordmark.png
docs/odysseus.svg          →  static/icons/odysseus.svg       (co-located with PWA icons)
docs/chat.gif              →  assets/chat.gif
docs/bg.webm               →  assets/bg.webm
... (all remaining demo media files)
```

The SVG goes to `static/icons/` because it is the application icon, not a README
screenshot. It belongs alongside the 192px and 512px PNG manifest icons, and
`manifest.json` is updated to reference it as `"sizes": "any"` for browsers that
support SVG icons. Build scripts (`build-linux-app.sh`, `build-freebsd-app.sh`,
`build-openbsd-app.sh`, `build-mac-app.sh`) are updated to read from `static/icons/`.

No functional changes to the running app. Pure file reorganization.

## Target branch

- [x] This PR targets **`dev`**, not `main`. All PRs land in `dev`; `main` is curated by the maintainer at each release.

## Linked Issue

Fixes # <!-- [file upstream issue first] -->

## Type of Change

- [ ] Bug fix (non-breaking, fixes a confirmed issue)
- [ ] New feature (non-breaking, adds new behaviour)
- [ ] Breaking change (changes or removes existing behaviour)
- [x] Refactor / cleanup (behaviour unchanged)
- [ ] Documentation only
- [ ] CI / tooling / configuration

## Checklist

- [x] I searched [open issues](https://github.com/pewdiepie-archdaemon/odysseus/issues) and [open PRs](https://github.com/pewdiepie-archdaemon/odysseus/pulls); this is not a duplicate.
- [x] This PR targets `dev`
- [x] My changes are limited to the scope described above; no unrelated refactors or whitespace changes mixed in.
- [x] I actually ran the app (`docker compose up` or `uvicorn app:app`) and verified the change works end-to-end. Type-checks and unit tests are not enough.
- [ ] **I am not an LLM agent submitting a bulk PR.** I reviewed and tested this change personally before submitting.

### How to Test

1. After merging, open `README.md`: verify all images render correctly (no broken image placeholders).
2. Verify the `assets/` directory exists at repo root and contains the moved media files.
3. Verify `static/icons/odysseus.svg` exists.
4. Verify `docs/` no longer contains the media files (`odysseus.jpg`, `odysseus.svg`, `chat.gif`, `bg.webm`, etc.).
5. Run `grep -r "docs/odysseus\|docs/chat\|docs/bg" README.md`: should return nothing (all references updated).
6. Open Settings → install the PWA: the icon should appear correctly on the home screen.
7. Run one of the platform build scripts (`build-linux-app.sh`): verify the icon installs without the `WARNING: No icon found` message.

---

## Filing Notes

- **File upstream issue first**: draft in `docs/fork/upstream/issue-drafts/refactor-assets-move.md`. Add the issue number to `Fixes #` above before opening the PR.
- No dependencies. Can be filed in any order.
- Build scripts are updated in this PR — no follow-up required for script breakage.

## Visual / UI changes

None; no HTML, CSS, or DOM-writing JS was changed.
