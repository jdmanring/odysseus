# Upstream Issue Draft: fix-sigcache-lru-bound

**File on:** `odysseus-dev/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/fix-sigcache-lru-bound.md`
**Branch:** `fix/sigcache-lru-bound`
**Type:** Performance

## Title
`perf(document): bound the _sigCache signature data-URL cache`

## Body
`static/js/document.js` `_sigCache = new Map()` stores signature `data_url`s (base64) and is never bounded; it only grows. `emailLibrary._libListCache` already uses an LRU cap; `_sigCache` should too. Low impact (bounded by # of signatures) but an unbounded cache is the wrong default.

**Fix:** add `_sigCacheSet` (max size + evict-oldest, mirroring `_libListCache`) and route all writes through it. Affected: `static/js/document.js`.
