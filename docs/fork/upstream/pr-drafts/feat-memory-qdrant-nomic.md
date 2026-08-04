# PR Draft: feat/memory-qdrant-nomic -> odysseus-dev/odysseus:dev

**Branch:** `feat/memory-qdrant-nomic`
**Status:** **HOLD** — do not file until `feat/memory-hybrid-recall` (#172) is
filed and its reception is known. This branch stacks on it.
**Base:** cut from `upstream-mirror`, 11 commits

---

## Title

`feat(memory): Qdrant + nomic vector backend`

---

## Summary

Replaces the ChromaDB memory vector store with Qdrant plus nomic embeddings.

### Why this is held rather than filed

Unlike everything else staged, **this is a product decision, not a defect fix.**
It swaps a dependency that upstream chose. A maintainer can reasonably decline it
while accepting every other memory improvement, and that is exactly why the
backend-independent half was split out first:

- `feat/memory-hybrid-recall` (#172) — hybrid BM25 + dense recall and write-time
  supersede, **zero `qdrant`/`chroma` references**, verified green on a pure
  upstream ChromaDB tree
- this branch — the backend swap, which stacks on it

Filing the swap first would put the fork's best memory work behind a dependency
argument. Filing it *at all* only makes sense once #172 has landed or been
discussed, because the answer to "do you want to change vector stores?" changes
what this PR should even contain.

**Recommended:** file #172, wait, then decide whether to file this, rewrite it as
a pluggable-backend proposal, or drop it and keep it fork-local.

### If it is filed

The case to make is the driver, which was **not** a preference for Qdrant as
such: FreeBSD support (ChromaDB does not install there) plus prior art from a
sibling project. The nomic embeddings are the part with a measured benefit; the
store swap is what made them deployable across the platforms the fork targets.

That framing is honest and much easier to accept than "we prefer Qdrant".

---

## Verification

**104 passed**, measured 2026-08-03, across the 18 test files the branch touches
that exist on it. It also **deletes 3** ChromaDB test files, which is the visible
shape of the swap and the thing a reviewer will react to first.

---

## Scope

11 commits: the Qdrant client, nomic embeddings, embedding lanes, `constants.py`
storage-dir changes, and the removal of the ChromaDB client and its tests.
