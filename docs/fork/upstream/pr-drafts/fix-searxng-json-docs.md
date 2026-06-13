# PR Draft: fix/searxng-json-docs → pewdiepie-archdaemon/odysseus:dev

**Branch:** `jdmanring/odysseus:fix/searxng-json-docs`
**Issue:** [#8](https://github.com/jdmanring/odysseus/issues/8) (fork tracking)
**Status:** Ready to file

---

## Title

`docs: document SearXNG JSON output requirement in .env.example`

---

## Description

### Problem

SearXNG's JSON output format is disabled by default in `settings.yml`. When a
user points `SEARXNG_INSTANCE` at a default SearXNG install, every search
request returns HTTP 404 with no useful error message. The only indication is
an opaque failure in the Odysseus search panel. There is currently no
documentation anywhere in the repository warning about this requirement.

### Fix

Add a comment block to `.env.example` immediately before the
`SEARXNG_INSTANCE` variable explaining the requirement and providing the
exact `settings.yml` snippet to enable JSON output:

```
# IMPORTANT: SearXNG must have JSON output enabled in its settings.yml, or all
# searches will return HTTP 404. Add to your SearXNG settings.yml:
#   search:
#     formats:
#       - html
#       - json
```

This is a documentation-only change — no runtime behavior is modified.

### How to Test

1. Open `.env.example` and locate the `SEARXNG_INSTANCE` variable.
2. Verify the comment block immediately above it explains the JSON output requirement and includes the exact `settings.yml` snippet.
3. No runtime behavior changed — this is a documentation-only change. No app restart required.

---

## Filing Notes (James)

- One commit, no squash needed.
- File issue on `pewdiepie-archdaemon/odysseus` first; add its number here
  before opening the PR.
