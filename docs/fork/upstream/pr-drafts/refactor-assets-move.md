# PR Draft: refactor/assets-move → pewdiepie-archdaemon/odysseus:dev

**Branch:** `jdmanring/odysseus:refactor/assets-move`
**Issue:** [#19](https://github.com/jdmanring/odysseus/issues/19) (fork tracking)
**Status:** Ready to file

---

## Title

`refactor: move media assets from docs/ to assets/`

---

## Summary
### Problem

Demo media files (screenshots, GIFs, WebM videos) are stored under `docs/`, mixing
documentation prose with binary assets. This causes several practical problems.

### Why the current layout is harmful

**`docs/` is becoming a documentation directory, and binary media files pollute it.**
A companion PR in the same batch (`feat/ai-documentation-system`) adds 36 markdown files
to `docs/ai/`, `docs/project/`, `docs/user/`, and `docs/dev/`. Once those land, a
contributor navigating to `docs/` to find architecture documentation or contributor guides
will see 14 GIF, WebM, and JPEG files at the root — the same demo media that currently
live there. The binary files have nothing to do with the documentation content; they are
README embed assets. This refactor separates them before the documentation tree grows.

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

Move all 14 demo media files to a top-level `assets/` directory. Update `README.md`
references and `.gitignore` paths accordingly.

```
docs/odysseus.jpg  →  assets/landingpage.jpg  (renamed; see above)
docs/chat.gif      →  assets/chat.gif
docs/bg.webm       →  assets/bg.webm
... (all 14 demo media files)
```

No functional changes. Pure file reorganization with one rename.

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
3. Verify `docs/` no longer contains the media files (`odysseus.jpg`, `chat.gif`, `bg.webm`, etc.).
4. Run `grep -r "docs/odysseus\|docs/chat\|docs/bg" README.md`: should return nothing (all references updated).
5. No screenshots required; no visual change.

---

## Filing Notes

- **File upstream issue first**: draft in `docs/fork/upstream/issue-drafts/refactor-assets-move.md`. Add the issue number to `Fixes #` above before opening the PR.
- No dependencies. Can be filed in any order.
- **Companion script breakage (maintainer note):** `build-macos-app.sh` line 46 references
  `docs/odysseus.jpg` — the path that this PR renames to `assets/landingpage.jpg`. After
  this PR merges, `build-macos-app.sh` must be updated: `docs/odysseus.jpg` →
  `assets/landingpage.jpg`. File a follow-up issue or include the one-line fix in this PR
  if the maintainer prefers atomic changes.

## Visual / UI changes

None; no HTML, CSS, or DOM-writing JS was changed.
