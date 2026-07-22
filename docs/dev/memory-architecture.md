# Memory / RAG architecture

Reference for how embeddings are produced and where vectors are stored across the
fleet. Locked in 2026-07-22.

## The stack

| Layer | Linux / Windows / macOS | FreeBSD |
|-------|-------------------------|---------|
| Embeddings | fastembed (nomic) | llama.cpp (nomic GGUF) |
| Vector store | Qdrant | Qdrant (native package) |

Embeddings and the vector store are separate concerns. The embedding backend turns
text into vectors; Qdrant stores and searches them. The backend can differ per
platform without the store caring, which is what lets FreeBSD swap ONNX for GGUF
while everything downstream stays identical.

## Embedding layer

### Model: nomic-embed-text-v1.5 (the `-Q` INT8 quant on fastembed)

768-dim, 8K-token context, roughly 130 MB at INT8, Apache-2.0.

It replaces `all-MiniLM-L6-v2`, which had been the default. all-MiniLM is a 2021
model with a 384-dim output and a 256-token context; nomic gives meaningfully better
retrieval and a 32x larger context window at a comparable footprint, and it is
trained for the asymmetric query/document prefixing we now use.

qwen3-embedding was considered and rejected. It isn't fastembed-supported (it's
decoder-based, not BERT-style), it's 4-5x heavier (595M vs 137M params), and its
advantages (multilingual coverage, 32K context) don't buy anything for a
single-user English workspace.

### Backend selection

`src/embedding_lanes.py::_build_fastembed_client()` tries fastembed first and falls
back to llama.cpp when fastembed can't load.

fastembed (ONNX) is the default wherever it runs: Linux, Windows, macOS. It's
Qdrant's own embedding library, so it pairs cleanly with the store.

llama.cpp (GGUF) is the fallback for platforms with no onnxruntime. fastembed's
runtime is onnxruntime, and onnxruntime has no FreeBSD Python binding: the port
ships the C++ library only, there is no wheel, and the source tree is a large build
FreeBSD doesn't target. `LlamaCppEmbedClient` runs the same nomic weights as a GGUF
through `py312-llama-cpp-python`, with mean pooling and L2 normalization. Both
backends apply the same nomic prefixes and Matryoshka truncation in `encode()` via
shared helpers, so the vectors line up regardless of which backend produced them.

Both expose the same `encode(texts, normalize_embeddings) -> (N, dim)` signature.

### Cross-platform vector compatibility

fastembed (INT8 ONNX) and llama.cpp (Q8 GGUF) are different quantizations of the
same nomic weights, so their vectors are about 0.96 cosine-compatible rather than
bit-identical. Each machine is self-consistent; the small drift only matters if
memory is ever synced across two machines running different backends, which the
current design doesn't do.

## Vector-store layer: Qdrant (replacing ChromaDB)

### Why the change

ChromaDB was the reason the memory system only worked on macOS. Two problems
compounded:

1. Chroma's server is a Python package whose default embedder is onnxruntime-based,
   so it hit the same FreeBSD wall as fastembed.
2. The "start and stop the database with the app" lifecycle was only ever written
   into `start-macos.sh`. Deployment otherwise assumed Docker (`docker-compose.yml`,
   which FreeBSD has no equivalent for) or a full native `chromadb` install driven
   by `chroma run`. On Linux, Windows, and FreeBSD nothing started a vector store at
   all, so the app silently fell back to keyword search. Semantic memory was, in
   practice, dead everywhere but macOS.

Qdrant removes both problems. It's a single Rust binary: no Python server, no
onnxruntime, no Docker. FreeBSD packages it directly (`qdrant` server plus
`py312-qdrant-client`), so it runs natively where Chroma couldn't. And because it's
one binary, the same start-and-reap lifecycle works identically on every platform,
which is what ends the macOS-only asymmetry. `qdrant-client` is a thin pure-Python
client, and fastembed being Qdrant's own library makes the embed-and-store pairing
the vendor's supported path.

### Prior art

This isn't a first attempt at the pattern. The private Qwen Code fork
(`megalonyx-monorepo`) already runs Qdrant as its memory store: local and cloud
tiers, cosine search, a write-ahead log with replay-on-startup recovery, all against
a local Qdrant instance driven by `QdrantClient`. That project validated the
single-binary local-Qdrant approach in real use before it was chosen here, and the
FreeBSD investigation is what surfaced it as the fix for Odysseus's Chroma problem
rather than a preference. The one deliberate difference: megalonyx used all-MiniLM
locally (384-dim) and a remote Gemini model for its cloud tier; Odysseus is
local-only and standardizes on nomic, since remote embedding is off the table here.

### Lifecycle

The app launches the Qdrant binary as a background process and reaps it on exit,
the same way on Linux, Windows, macOS, and FreeBSD. It connects over
`qdrant-client` (default `:6333`), overridable with `QDRANT_HOST` / `QDRANT_PORT`.

## Optimized-nomic configuration

nomic is run for what it is, not as a drop-in all-MiniLM. Three settings, all
implemented alongside the Qdrant migration:

**Matryoshka truncation to 256-dim.** nomic-v1.5 is trained so the leading
dimensions carry the most signal, so both backends keep the first 256 of the 768
output dimensions and re-normalize. That's a 3x cut in vector size and search cost
for roughly a 1-2% retrieval hit. Qdrant collections are created at 256-dim.
`EMBEDDING_TRUNCATE_DIM` (default 256) tunes it.

**Asymmetric query/document prefixes.** Queries get `search_query:`, stored
documents get `search_document:`, applied at the two encode call sites that already
distinguish the two. nomic is trained on exactly this split, and it measurably
sharpens retrieval. Both backends apply the prefixes identically so vectors stay
aligned across platforms.

**Chunk size tuned to nomic, not maxed to its context.** The old `CHUNK_SIZE = 1000`
chars (about 250 tokens, in `src/personal_docs.py` and `src/rag_vector.py`) was a
leftover from all-MiniLM's 256-token limit. It's now 2048 chars, roughly 512 tokens,
with 300 chars of overlap. The point is deliberately *not* to fill nomic's 8K
context per chunk: a large chunk averages many sentences into one vector and dilutes
what the vector points at, so retrieval gets worse, not better. ~512 tokens is the
sweet spot between capturing enough context and keeping each vector about one idea.

## Status

Done and validated:

- nomic is the default embedder (`0f14f238`).
- fastembed to llama.cpp auto-fallback works on host and FreeBSD (`c1101bcd`).
- The install-time verifier recognizes both backends (`c22a0408`).
- Optimized nomic: 256-dim Matryoshka truncation, query/document prefixes, and the
  2048-char chunk size, applied identically by both backends (`f1bbda86`). Validated
  on the host: 256-dim output, prefixes active (query vs document cosine 0.827), and
  sharper retrieval (best match 0.931 against the earlier 0.52).
- `qdrant-client` added as a dependency (`77f4e6a5`).

In progress, the Chroma-to-Qdrant swap:

- Scope is a bounded backend change. About five files own the Chroma coupling
  (`src/chroma_client.py`, `embedding_lanes.py`, `memory_vector.py`,
  `rag_vector.py`, plus a few call sites) behind a small collection API: create,
  upsert, search, get, count, delete.
- No data migration is needed, since memory was never actually persisting.
- Plan: a thin `VectorStore` abstraction with a Qdrant implementation, plus the
  uniform binary lifecycle. Chroma is being removed outright rather than kept behind
  the interface, since nothing depends on the stored data.
- Upstream-candidate. Tracked under its own issue and branch (#161).
