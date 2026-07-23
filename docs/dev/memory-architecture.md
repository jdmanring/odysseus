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

The migration started from a concrete need: a vector store that runs on FreeBSD.
ChromaDB does not. Its server is a Python package whose default embedder is
onnxruntime-based, and onnxruntime has no FreeBSD Python binding — the same wall
fastembed hits. There is no native FreeBSD deployment path for it.

Investigating the FreeBSD requirement surfaced the answer from prior work rather
than a fresh search: the local-embedding + Qdrant stack from the private Qwen Code
fork (`megalonyx-monorepo`) fits Odysseus just as well. Qdrant is a single Rust
binary — no Python server, no onnxruntime, no Docker — and FreeBSD packages it
directly (`qdrant` server plus `py312-qdrant-client`), so it runs natively where
Chroma cannot. `qdrant-client` is a thin pure-Python client, and fastembed is
Qdrant's own embedding library, so the embed-and-store pairing is vendor-matched.

Recognizing those components pointed to a fleet-wide upgrade rather than a
FreeBSD-only patch: adopt the same store everywhere, including the pattern of
starting and stopping the store binary alongside the app on every platform. That
start/stop lifecycle is carried over from the Qwen fork, where it was already
built; it is not inherited from this repo's `start-macos.sh`.

### Prior art

The Qwen Code fork (`megalonyx-monorepo`) already runs this stack: Qdrant as the
memory store with local and cloud tiers, cosine search, and a write-ahead log with
replay-on-startup recovery, all against a local Qdrant instance driven by
`QdrantClient`, plus the start/stop-with-the-app lifecycle. That project is where
the single-binary local-Qdrant approach — and its lifecycle mechanics — were proven
in use, which is why the FreeBSD investigation landed on it directly. The one
deliberate difference: megalonyx used all-MiniLM locally (384-dim) with a remote
Gemini model for its cloud tier; Odysseus is local-only and standardizes on nomic,
since remote embedding is off the table here.

### Lifecycle

`qdrant-client` runs Qdrant in **embedded local mode** by default —
`QdrantClient(path=DATA_DIR/qdrant)` (`src/vector_client.py`), an in-process,
on-disk store that comes up with the app (uvicorn) and is released when it exits.
There is no separate server process, port, or binary to manage: vector access
here is single-process, which is exactly what local mode requires. Setting
`QDRANT_HOST` (with optional `QDRANT_PORT`, default 6333) switches to server mode
against an external Qdrant instead — the opt-in path for a shared instance.

This **supersedes** the originally-planned "start/stop the Qdrant binary alongside
the app" lifecycle (carried over from the Qwen fork): that launcher was never
built, and embedded mode makes it unnecessary — nothing to download, pin, or reap,
and it works on every platform, **including OpenBSD, which has no Qdrant server
binary at all**. On a crash the local store's lock is released with the process
(verified: a SIGKILLed holder does not block the next start).

Qdrant has no free-form collection metadata, so the per-lane embedding
*fingerprint* (which detects a model/dimension/endpoint change and triggers a
collection rebuild) is tracked in a local sidecar, `vector_fingerprints.json`
under the data dir, rather than on the collection.

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

- nomic is the default embedder.
- fastembed to llama.cpp auto-fallback works on host, FreeBSD, and OpenBSD.
- The install-time verifier recognizes both backends.
- **Embedded local Qdrant is the default** (see Lifecycle); memory comes up
  healthy when the app runs, verified end-to-end on the Linux host and OpenBSD.
- Optimized nomic: 256-dim Matryoshka truncation, query/document prefixes, and the
  2048-char chunk size, applied identically by both backends. Validated
  on the host: 256-dim output, prefixes active (query vs document cosine 0.827), and
  sharper retrieval (best match 0.931 against the earlier 0.52).
- `qdrant-client` added as a dependency.
- The Chroma-to-Qdrant store swap. `src/vector_client.py` is a
  Chroma-shaped adapter over `QdrantClient`; the six Chroma call sites moved onto
  it and ChromaDB was removed outright (no data to migrate — nothing persisted).
  The adapter converts Qdrant's similarity score back to a Chroma-style cosine
  distance, maps arbitrary string IDs to UUIDs, and translates `where=` equality
  filters. Validated against a live Qdrant 1.18.3 with real nomic (256-dim):
  MemoryVectorStore (semantic recall ranks correctly; add/remove/rebuild) and
  VectorRAG (owner-filter isolation, hybrid ranking, delete-by-source).

### OpenBSD memory stack (self-contained, no onnxruntime, no grpcio)

OpenBSD reaches the same local stack as FreeBSD, but two PyPI deps have no OpenBSD
path and need explicit provisioning (`tooling/provision_bsd_memory.sh`, called by
`setup.sh`; idempotent):

- **Embedding — llama.cpp GGUF, built from source.** onnxruntime has no BSD build,
  so fastembed can't run; `llama-cpp-python` compiles cleanly (`GGML_NATIVE=OFF`).
  Two OpenBSD-only fix-ups after the build: its loader's platform allowlist names
  linux/freebsd but not openbsd (openbsd loads `.so` the same way), and OpenBSD's
  linker leaves the shared libs versioned (`libX.so.N`) without the unversioned
  `libX.so` symlink the ctypes loader expects. The nomic GGUF is fetched from
  HuggingFace on first run (`huggingface-hub`, installed without its Rust `hf-xet`
  accelerator, which also won't build).
- **Vector client — grpc import stub.** `qdrant-client` hard-imports `grpc`, and
  grpcio has no OpenBSD wheel (its bundled `upb` fails to compile; a system-libs
  build clears the LibreSSL wall but still dies on `upb`). Local mode never speaks
  gRPC at runtime, so a vendored import-only stub (`tooling/bsd/grpc_stub`) is
  installed only when real grpcio is absent. The llama.cpp OpenBSD loader fix is
  also a legitimate upstream contribution to `llama-cpp-python` (it already
  supports FreeBSD).

Still pending:

- Upstream-candidate. Tracked under its own issue and branch (#161).
