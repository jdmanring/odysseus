# [UPSTREAM] SearXNG JSON Format Not Documented in .env.example

## Status
- Issue filed: Not yet filed
- PR opened: Not yet opened
- Fix in fork: Documented in fork runbooks; user's own SearXNG instance is configured correctly

## Notes
Docs-only change. No app code touches. No screenshot needed.

---

## Staged Issue
<!-- James: open https://github.com/pewdiepie-archdaemon/odysseus/issues/new?template=bug_report.yml and paste below -->

**Steps to Reproduce**

1. Set up a self-hosted SearXNG instance using its default configuration.
2. Set `SEARXNG_INSTANCE=http://your-instance` in `.env`.
3. Use Odysseus web search.

**Expected Behaviour**

Web search returns results from SearXNG.

**Actual Behaviour**

All search requests fail with HTTP 404. SearXNG returns 404 for `/search?format=json`
because JSON output is disabled in SearXNG's default configuration.

**Root Cause**

SearXNG disables JSON output by default. Enabling it requires adding `formats: [html, json]`
under the `search:` key in SearXNG's `settings.yml`. Odysseus queries the JSON API
exclusively (`/search?format=json`). The `.env.example` comment for `SEARXNG_INSTANCE`
does not mention this requirement, so users following the setup guide will encounter
silent failures with no obvious error message.

**Proposed Fix**

Add a comment to `.env.example`:

```bash
# SearXNG instance URL (self-hosted).
# IMPORTANT: your SearXNG settings.yml must include:
#   search:
#     formats:
#       - html
#       - json
# SearXNG disables JSON output by default and Odysseus queries the JSON API exclusively.
SEARXNG_INSTANCE=http://localhost:8080
```

**Install Method:** Manual Python install

**OS:** Linux

**Willing to submit a fix:** Yes — I can open a PR

---

## Staged PR
<!-- James: file the issue first, get the number, fill in Fixes #NNN below, then open PR -->

### Summary

SearXNG disables JSON output by default. Odysseus queries only the JSON API. Users
following the setup docs will get 404 errors on every search with no clear explanation.
Fix: add one comment to `.env.example` explaining the required SearXNG config.

### Target branch
- [x] This PR targets **`dev`**, not `main`.

### Linked Issue

Fixes #

### Type of Change
- [x] Documentation only

### Checklist
- [x] Searched open issues and open PRs — not a duplicate
- [x] Targets `dev`
- [x] Changes limited to described scope
- [ ] App run locally and search verified with a fresh SearXNG instance *(must do before filing)*

### How to Test

1. Deploy a fresh SearXNG instance with default config (no JSON format enabled).
2. Set `SEARXNG_INSTANCE` in `.env`.
3. Trigger a web search — confirm the error message or 404.
4. Add `formats: [html, json]` to SearXNG `settings.yml`.
5. Search again — confirm results return.
6. The `.env.example` comment now explains step 4.

### Visual / UI changes

None — `.env.example` comment only.
