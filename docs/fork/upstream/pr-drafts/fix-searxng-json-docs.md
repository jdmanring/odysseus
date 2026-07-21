# PR Draft: fix/searxng-json-docs → odysseus-dev/odysseus:dev

**Branch:** `fix/searxng-json-docs`
**Issue:** [#8](https://github.com/jdmanring/odysseus/issues/8) (fork tracking)
**Status:** Ready to file

---

## Title

`docs: document SearXNG JSON output requirement in .env.example`

---

## Summary
### Problem

SearXNG's JSON output format is disabled in its default `settings.yml`. When a user
points `SEARXNG_INSTANCE` at a stock SearXNG install, every search request Odysseus
makes returns HTTP 404. There is no useful error message anywhere in the Odysseus UI —
only a blank or failed search result.

### Who is affected and why it's a trap

This affects **every user who self-hosts SearXNG and follows SearXNG's own installation
guide**, which does not mention enabling JSON output because that requirement is specific
to API consumers. The SearXNG web interface works fine without JSON; HTML output is
enough to render a search page in a browser. Users have no reason to know the JSON
format must be explicitly enabled; it is an invisible Odysseus-specific prerequisite
with no indication it is missing.

The typical debugging path for a user hitting this:

1. Odysseus search fails silently; assume it's a network problem
2. Verify SearXNG is running; it is, the web interface works fine
3. Check Odysseus logs; see HTTP 404 from SearXNG with no explanation
4. Search for "odysseus searxng 404"; either find nothing, or find a GitHub issue
5. Eventually discover the JSON format requirement by reading SearXNG's API docs

Without the comment, users hit HTTP 404 from a working SearXNG install with no
indication that JSON output must be explicitly enabled — it is an Odysseus-specific
prerequisite that SearXNG's own installation guide does not mention.

There is currently **no documentation anywhere in the repository** about this
requirement. It is not in the README, not in `.env.example`, not in any guide. The only
way to know is to have been burned by it.

### Fix

Add a comment block to `.env.example` immediately before `SEARXNG_INSTANCE` with the
exact `settings.yml` snippet needed:

```
# IMPORTANT: SearXNG must have JSON output enabled in its settings.yml, or all
# searches will return HTTP 404. Add to your SearXNG settings.yml:
#   search:
#     formats:
#       - html
#       - json
```

Documentation-only change. No runtime behavior modified. Zero risk.

## Target branch

- [x] This PR targets **`dev`**, not `main`. All PRs land in `dev`; `main` is curated by the maintainer at each release.

## Linked Issue

Fixes # <!-- [file upstream issue first] -->

## Type of Change

- [ ] Bug fix (non-breaking, fixes a confirmed issue)
- [ ] New feature (non-breaking, adds new behaviour)
- [ ] Breaking change (changes or removes existing behaviour)
- [ ] Refactor / cleanup (behaviour unchanged)
- [x] Documentation only
- [ ] CI / tooling / configuration

## Checklist

- [x] I searched [open issues](https://github.com/odysseus-dev/odysseus/issues) and [open PRs](https://github.com/odysseus-dev/odysseus/pulls); this is not a duplicate.
- [x] This PR targets `dev`
- [x] My changes are limited to the scope described above; no unrelated refactors or whitespace changes mixed in.
- [x] I actually ran the app (`docker compose up` or `uvicorn app:app`) and verified the change works end-to-end. Type-checks and unit tests are not enough.
- [ ] **I am not an LLM agent submitting a bulk PR.** I reviewed and tested this change personally before submitting.

### How to Test

1. Open `.env.example` and locate the `SEARXNG_INSTANCE` variable.
2. Verify the comment block immediately above it explains the JSON output requirement and includes the exact `settings.yml` snippet.
3. No runtime behavior changed; this is a documentation-only change. No app restart required.

---

## Filing Notes

- One commit, no squash needed.
- **File upstream issue first**: draft in `docs/fork/upstream/issue-drafts/fix-searxng-json-docs.md`. Add the issue number to `Fixes #` above before opening the PR.

## Visual / UI changes

None; no HTML, CSS, or DOM-writing JS was changed.
