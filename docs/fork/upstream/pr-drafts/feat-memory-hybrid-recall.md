# PR Draft: feat/memory-hybrid-recall -> odysseus-dev/odysseus:dev

**Branch:** `feat/memory-hybrid-recall`
**Issue:** #172 (fork tracking, `docs/fork/issues/INDEX.md`)
**Status:** Ready to file
**Base:** cut from `upstream-mirror`, three commits (`514c54a1`, `b4f546bd`,
`b8730071`), 10 files, +615/-16

---

## Title

`feat(memory): hybrid BM25 + dense recall and write-time supersede`

---

## Summary

### Problem

`NativeMemoryProvider.recall()` returns whatever the vector store ranks highest.
Pure dense retrieval has two failure modes that show up constantly in an agent's
memory, because agent memories are short and full of proper nouns:

**Rare tokens get washed out.** A memory containing a specific identifier (a
hostname, a package name, a person's handle) is retrieved by semantic similarity
to the query as a whole. Embeddings compress exactly the low-frequency tokens
that make the memory findable. Query "what port does the staging box use" against
a store holding "staging-7 listens on 8443" competes against every other memory
that is broadly about ports and boxes.

**Stale memories outrank current ones.** Nothing in the write path notices that a
new memory contradicts an old one. "prefers dark mode" written in March and
"switched to light mode" written in July both sit in the store at comparable
similarity to "what theme do they use", and which one surfaces is arbitrary.

**Every recall path answers differently.** Chat context injection hand-rolled a
binary-tf BM25; the agent's recall tool, the MCP memory server and the memory
search API used a keyword-category heuristic or vector-only ranking. Three
schemes for one question, so the same query against the same store returns a
different ordering depending on which entry point asked.

### What this changes

Two pieces, plus the consolidation:

**1. Hybrid recall (`src/memory_ranking.py`).** BM25 over the memory text fused
with the dense scores the vector store already returns. Lexical matching recovers
the rare-token case; the dense half keeps paraphrase recall. The provider
over-fetches (`min(top_k * 3, 20)`) so fusion has candidates to reorder, then
truncates to `top_k`.

**2. Write-time supersede (`src/memory_supersede.py`).** On write, a new memory is
compared against existing ones; a sufficiently close match is marked superseded
rather than left to compete at read time. Superseded entries are filtered inside
`hybrid_search`, so every recall path gets the behaviour from one place rather
than each caller remembering to filter.

**3. One ranking implementation.** `hybrid_search` is wired into
`NativeMemoryProvider`, `ai_interaction`'s recall tool, the MCP memory server,
and the memory search route. Each is guarded on a healthy vector store and falls
back to `get_relevant_memories` exactly as before when there is none, so a
deployment without a vector store sees no behaviour change at all.

The chat hot path is deliberately **not** rewritten onto it. It keeps its own
tokenizer and category boosts, which are live-tested, and shares the fusion shape
and the superseded filter. Fusion weights (0.55 dense / 0.40 lexical / 0.05
recency tiebreak) are the chat path's own values, so the shared implementation
starts from what was already in production rather than from a guess.

Supersede results ride back on the returned record's `metadata["supersede"]`
(`superseded` and `candidates`), so a caller that wants to surface or undo the
decision can, and one that does not care is unaffected.

### Fit with the provider interface

This lands inside `NativeMemoryProvider.remember()` / `.recall()`, the extension
point the `MemoryProvider` ABC exists to provide. No changes to the ABC, the
registry, or any other provider. A provider that does its own ranking is
untouched.

---

## What the lexical half is supported by

**The lift is confirmed at multiseed.** Blend weight chosen by stratified 5-fold
CV on train folds only, then held out; five fresh filler pools at those
pre-registered alphas, not re-tuned, pool to **16-3 discordant (p = 0.0044, exact
sign test)** for nomic and 20-5 (p = 0.0041) for EmbeddingGemma-300m. The lift
lands where the mechanism predicts: per-section, essentially all of it is in the
stale section (0.54 -> 0.67 for gemma), and every other section is unchanged.
Current facts carry temporal language ("switched", "as of", "now") that lexical
scoring bridges to now-queries and dense similarity underweights.

An earlier single-pool run read 4-1 discordant, p = 0.375, and was reported as
directionally-real-but-unproven; the multi-pool study superseded it. Both states
of the evidence are kept in the source rather than the old one being quietly
dropped.

**One caveat, stated because the benchmark states it.** The effect size is partly
an artifact of corpus construction: the benchmark's stale items were authored
with temporal markers. Real memories carry them too, which is why the mechanism
is expected to transfer, but **the magnitude should not be quoted as a general
number** and this PR does not quote one. What transfers is the direction and the
mechanism, not "+2 points R@1".

Source and reproduction: the benchmark is a separate suite of the author's;
`benchmark/hybrid_dense.py` regenerates the study, and the numbers are recorded
in its `results/hybrid-dense.md` and `results/score-levers.md` part 5.
`docs/dev/memory-architecture.md` in this repo carries the same figures.

Two negatives measured alongside, recorded so they do not get re-litigated:

- Widening the Matryoshka truncation past 256 dims buys nothing (R@1 flat from
  128 to 768 at 140-query resolution).
- Stock cross-encoder rerankers *hurt* memory-shaped retrieval
  (`bge-reranker-base` 11-30 against dense order, p = 0.004). The rerank headroom
  is real (recall@10 = 0.971) but harvesting it needs a domain-tuned reranker.

Cost, separately from lift: BM25 here is arithmetic over text already in memory.
No new dependency, no index, no service, no model, sub-millisecond at
memory-store scale. Weights are per-call, so a path with live-tested values keeps
them.

The consolidation stands independently of all of this. If the BM25 weight were
set to zero tomorrow, the "same query ranks differently depending on which entry
point asked" defect stays fixed.

---

## Contract change a reviewer will ask about

`test_native_provider_recall_filters_vector_hits_by_owner` asserted
`hits[0].score == 0.75`, the raw vector similarity passed straight through. With
fusion the score is a blended BM25 + dense value and legitimately differs. The
test now asserts bounds (`0.75 <= score <= 1.0`) instead of a bare equality.

**Owner isolation, which is what that test is for, is unchanged and still
asserted.** The fixture gives bob's memory a higher raw score (0.99) than
alice's; it must still not surface for alice, and the identity assertion
(`[hit.memory.id] == [alice.id]`) is untouched.

If pinning an exact score is preferred, say so and it can be recomputed and
pinned - but the previous value was an implementation detail of the vector store,
not a documented part of the recall contract.

## Behaviour deliberately preserved

A stale index can return rows that are whole entries (`id`/`text`, no
`memory_id`) with no JSON counterpart. Those carried real user data before this
change. Rather than let fusion drop them, they are salvaged and appended after
the fused hits. This is the same allowance the pre-change code made implicitly by
falling back to `entry = result`; it is now explicit and commented, and it does
not displace properly-indexed results.

---

## Verification

- **109 passed** across the full `-k memory` selection, on a tree that is
  otherwise pure `upstream-mirror` (so: ChromaDB, upstream's own backend).
- **16/16** on `test_memory_ranking.py` + `test_memory_supersede.py` specifically.
- **258 passed** across `-k "memory or ai_interaction or mcp"` after the three
  additional call sites were wired.
- **Zero `qdrant` / `chroma` references in the entire diff**, verified by grep
  over the diff, not assumed. The only vector-store contact is
  `memory_vector.search(query, k=...)`, whose signature and return shape
  (`{"memory_id": str, "score": float}`) are identical on both backends.

The backend-independence claim matters because this work was originally developed
alongside a vector-backend swap. It was split out and re-verified against
upstream's backend precisely so that reviewing it does not require an opinion on
the backend.

---

## Files

| File | Change |
|---|---|
| `src/memory_ranking.py` | new; BM25 + dense fusion, superseded filtering |
| `src/memory_supersede.py` | new; write-time supersede detection |
| `src/memory_provider.py` | `remember()` / `recall()` hooks (+47/-12) |
| `src/memory.py` | superseded filtering in the keyword fallback (+3) |
| `src/ai_interaction.py` | agent recall tool -> `hybrid_search` |
| `mcp_servers/memory_server.py` | MCP search action -> `hybrid_search` |
| `routes/memory/memory_routes.py` | memory search API -> `hybrid_search` |
| `tests/test_memory_ranking.py` | new |
| `tests/test_memory_supersede.py` | new |
| `tests/test_memory_provider.py` | score assertion -> bounds (see above) |

---

## Not in this PR

The Qdrant + nomic vector backend that this was split out of. That is a product
decision with its own tradeoffs and belongs in a separate discussion; it stacks
on this branch and does not block it.
