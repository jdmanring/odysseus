# PR Draft: fix/chat-history-dom-eviction (commit 2: eviction graft)

**Branch**: `fix/chat-history-dom-eviction` (from `upstream-mirror`), commit 2 of 2.
**Fork issue**: jdmanring/odysseus#2 (reframed; needs reopening; currently CLOSED).
**Depends on**: commit 1 (route-shadowing fix, `fix-history-route-shadowing.md`).
**Status**: staged + verified end-to-end. NOT filed.

## Title

perf(history): bound chat-history DOM by evicting oldest paged message nodes

## Problem

The maintainer's history pager (`45ee5a71`) only *adds* older messages on scroll-up
(`insertBefore`), and streaming appends newer ones, so a long paged session grows
the DOM without bound. The pager never evicts.

## Approach: a graft, not a rewrite

Rather than replace the pager (an earlier fork branch tried to port a 916-line
`MessageWindow`; abandoned; see `fix-dom-oom-virtualization.md`), add a small
eviction pass that composes with the existing pager:

- **Tag** each primary node (`.msg, .agent-thread, .gallery-bubble`) with its
  absolute DB row offset at both render sites (initial load, pager prepend).
- **Evict**: when primaries exceed `MAX_LIVE_HISTORY_NODES` (240) and the user has
  scrolled down (top nodes off-screen), remove the oldest primaries (tearing down
  the app's own per-node handles: `_waveInterval`, `_elapsedTicker`,
  `_streamRenderer`, `_spinner`), then set `_historyPager.offset` to the new topmost
  node's tag and clear `done`.
- **Refetch**: scroll-up hits the pager, which refetches exactly the evicted rows.

The offset tag means eviction reads a single contiguity invariant instead of
counting, robust to multi-node messages and filtered-null rows (which a
count-based rewind would misalign at).

## Scope / honest claims

- **In scope:** any session loaded with `has_more_before` (a pager exists -> evicted
  nodes are refetchable).
- **Out of scope (documented limitation):** a session that loads short then streams
  into a marathon has no pager and untagged live nodes; symmetric eviction for that
  is follow-up.
- **What this validates:** correctness (no gap/duplicate at the seam) and a bounded
  live node count -> responsiveness + memory on standard browsers. It does **not**
  claim an RSS fix; in QtWebEngine an evicted node becomes a *detached* node Oilpan
  won't reclaim without `gc()`/pressure, so this is not by itself a QtWebEngine OOM
  fix (that is separate reclaim work).

## Attribution

Written independently. The teardown resembles nothing borrowed; the only lines
that look like open PR #4661's `_trimChatHistoryDOM` clear this app's own
`_waveInterval`/`_elapsedTicker` fields (one obvious way, forced by the codebase).
We rejected #4661's method wholesale. No in-code attribution. Coordination reference
is the maintainer's pager commit `45ee5a71`, which this composes with.

## Verification

`tests/test_chat_history_eviction_playwright.py::test_eviction_seam_no_gap_no_duplicate`
boots the real app in Chromium against a seeded 420-row session **with
filtered-null rows interleaved** (so DB offsets diverge from the visible sequence,
the case that distinguishes offset-tagging from counting). Asserts: paging stays
contiguous, eviction bounds the DOM to the cap, and the eviction/refetch seam has no
gap or duplicate.
