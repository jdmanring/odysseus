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

**Documentation tooling requires workarounds.** Static site generators
(Docusaurus, MkDocs, Sphinx) and search indexers that scan `docs/` for content
encounter multi-megabyte GIF and WebM files alongside Markdown. These tools require
explicit exclusion configuration to skip binary files — configuration that is not
present in the repo. Adding a documentation site in the current layout means
writing exclude rules before a single page can be built.

**Git history is polluted.** Binary files in `docs/` appear in every `git log --stat`
and `git diff --stat` that touches the documentation. Any change to a GIF produces an
uninformative binary diff. Tools that blame or annotate documentation files include
binary noise in the results.

**`docs/odysseus.jpg` causes a thumbnail collision with the app icon.** The Qt taskbar
uses `odysseus.svg` as the application icon. Because `docs/odysseus.jpg` shares the same
base name, file pickers and system thumbnail caches that scan the project directory use
the landing page screenshot as the app thumbnail instead of the vector icon. Renaming to
`landingpage.jpg` removes the collision.

**Industry standard practice.** Major open-source projects (VSCode, Electron, React,
FastAPI) separate code/docs from binary media using a top-level `assets/` directory.
Odysseus following this convention makes the repository layout immediately recognisable
to contributors familiar with these projects.

### Change

Move all 17 demo media files to a top-level `assets/` directory. Update `README.md`
references and `.gitignore` paths accordingly.

```
docs/odysseus.jpg  →  assets/landingpage.jpg  (renamed — see above)
docs/odysseus.svg  →  assets/odysseus.svg
docs/chat.gif      →  assets/chat.gif
docs/bg.webm       →  assets/bg.webm
... (all demo media)
```

No functional changes. Pure file reorganization with one rename.

## Target branch

- [x] This PR targets **`dev`**, not `main`. All PRs land in `dev`; `main` is curated by the maintainer at each release.

## Linked Issue

Fixes # <!-- [file upstream issue first] -->

## Type of Change

- [ ] Bug fix (non-breaking — fixes a confirmed issue)
- [ ] New feature (non-breaking — adds new behaviour)
- [ ] Breaking change (changes or removes existing behaviour)
- [x] Refactor / cleanup (behaviour unchanged)
- [ ] Documentation only
- [ ] CI / tooling / configuration

## Checklist

- [x] I searched [open issues](https://github.com/pewdiepie-archdaemon/odysseus/issues) and [open PRs](https://github.com/pewdiepie-archdaemon/odysseus/pulls) — this is not a duplicate.
- [x] This PR targets `dev`
- [x] My changes are limited to the scope described above — no unrelated refactors or whitespace changes mixed in.
- [x] I actually ran the app (`docker compose up` or `uvicorn app:app`) and verified the change works end-to-end. Type-checks and unit tests are not enough.
- [ ] **I am not an LLM agent submitting a bulk PR.** I reviewed and tested this change personally before submitting.

### How to Test

1. After merging, open `README.md` — verify all images render correctly (no broken image placeholders).
2. Verify the `assets/` directory exists at repo root and contains the moved media files.
3. Verify `docs/` no longer contains the media files (`odysseus.jpg`, `chat.gif`, `bg.webm`, etc.).
4. Run `grep -r "docs/odysseus\|docs/chat\|docs/bg" README.md` — should return nothing (all references updated).
5. No screenshots required — no visual change.

---

## Filing Notes

- **File upstream issue first** — draft in `docs/fork/upstream/issue-drafts/refactor-assets-move.md`. Add the issue number to `Fixes #` above before opening the PR.
- No dependencies. Can be filed in any order.

## Visual / UI changes

None — no HTML, CSS, or DOM-writing JS was changed.
