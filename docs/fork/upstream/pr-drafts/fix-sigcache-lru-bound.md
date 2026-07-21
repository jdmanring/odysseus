# Upstream PR Draft: fix-sigcache-lru-bound

**Branch:** `fix/sigcache-lru-bound` (from `upstream-mirror`)
**Target:** `odysseus-dev/odysseus:dev`
**Fixes:** #_ (file issue-drafts/fix-sigcache-lru-bound.md first)
**Filing notes:** Single concern, JS-only.

## Title
`perf(document): bound _sigCache with an LRU cap`

## Description
`_sigCache` stored base64 data URLs with no cap. Add `_sigCacheSet` (max 200, refresh-on-write, evict-oldest), mirroring `emailLibrary._libListCache`, and route all four write sites through it.

## Tests
`tests/test_sigcache_bound.py` (2 guards): helper defines cap + eviction; all writes go through the bounded helper (only the helper retains a raw `.set`).

## Risk
Low — behaviour identical below the cap; oldest entries re-fetch lazily if evicted.
