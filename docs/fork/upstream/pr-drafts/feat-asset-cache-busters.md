# PR Draft: feat/asset-cache-busters -> odysseus-dev/odysseus:dev

**Branch:** `feat/asset-cache-busters`
**Status:** Ready to file
**Base:** cut from `upstream-mirror`, 2 files, +111

---

## Title

`feat(assets): derive static ?v= cache-busters from content hashes at serve time`

---

## Summary

### Problem

Static assets are cache-busted with hand-maintained `?v=` pins in the HTML. That
makes correctness depend on a human remembering to bump a number in a different
file from the one they edited.

When it is forgotten, every client keeps serving the **old** asset from cache and
there is no error anywhere. A restored stylesheet looked broken for an hour
because clients were still on the cached previous version.

The failure mode is also asymmetric: the person who made the change usually has a
warm dev cache or hard-refreshes, so they see the fix and everyone else does not.

### Fix

`serve_html_with_nonce` rewrites `/static/*?v=` pins to a **12-character content
hash** at serve time, cached by mtime so it is not a hash-per-request.

The correctness property: the pin now *derives from the bytes*, so it cannot
disagree with them. Forgetting to bump becomes impossible rather than merely
discouraged.

**Fails open.** An asset that cannot be read keeps its hand-written pin. A
cache-busting mechanism must never be able to prevent a page from serving, so the
degraded path is the current behaviour rather than an error.

### Why serve time rather than a build step

Odysseus has no asset build step, and adding one to solve this would be a much
larger change than the problem justifies. Hashing on read, memoised by mtime,
costs one `stat` per asset per request in the warm case.

---

## Verification

**6 passed**, measured 2026-08-03. The tests cover the rewrite, the mtime cache,
and the fail-open path for a missing asset.

---

## Scope

`src/app_helpers.py` (+47), one test file (+64). No template changes: existing
hand-written pins keep working and are simply superseded by the derived value.
