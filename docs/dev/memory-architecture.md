# Memory / RAG architecture

Locked-in architecture for the semantic-memory and RAG stack (decided 2026-07-22).
This is the reference for how embeddings are produced and where vectors are stored
across the fleet.

## The stack (locked in)

| Layer | Linux / Windows / macOS | FreeBSD |
|-------|-------------------------|---------|
| **Embeddings** | fastembed (nomic) | llama.cpp (nomic GGUF) |
| **Vector store** | **Qdrant** | **Qdrant** (native Rust binary, packaged) |

Embeddings and the vector store are **orthogonal layers**: the embedding backend
turns text into vectors; Qdrant stores and searches them. The backend can differ
per platform without affecting the store.

**Optimized-nomic configuration (locked in):** nomic is run *fully*, not like a
drop-in all-MiniLM replacement:
- **Vectors truncated to 256-dim** via Matryoshka (from 768) — 3× smaller/faster,
  ~1–2% quality cost. Qdrant collections are 256-dim.
- **Asymmetric prefixes** — `search_query:` for queries, `search_document:` for
  documents (nomic is trained for this; improves retrieval).
- **Chunk size sized for nomic's 8K context**, not all-MiniLM's 256-token fossil.

---

## Embedding layer

### Model: `nomic-embed-text-v1.5` (the `-Q` INT8 quant on fastembed)

- 768-dim, **8K token context**, ~130 MB (INT8), Apache-2.0.
- Chosen over the previous default `all-MiniLM-L6-v2` (2021-era, 384-dim, 256-token
  context): meaningfully better retrieval and a 32× larger context window at a
  comparable footprint.
- Chosen over `qwen3-embedding`: qwen3 is **not** fastembed-supported (decoder-based,
  not BERT-style), 4–5× heavier (595M vs 137M), and its wins (multilingual, 32K
  context) aren't needed for this workspace. nomic is the right fit.

### Backend selection (automatic)

`src/embedding_lanes.py::_build_fastembed_client()` tries fastembed first and falls
back to llama.cpp when fastembed can't load:

- **fastembed (ONNX)** — the default everywhere it works (Linux/Windows/macOS).
  fastembed is made by Qdrant, so it pairs natively with the store.
- **llama.cpp (GGUF)** — the onnxruntime-free fallback. fastembed's runtime is
  onnxruntime, which has **no FreeBSD Python binding** (the pkg ships only the C++
  library; there is no wheel, and the source build is a large project FreeBSD
  doesn't target). `LlamaCppEmbedClient` runs the *same* nomic model as a GGUF via
  `py312-llama-cpp-python`, with mean pooling + L2 normalization and **no task
  prefix** (verified empirically to match fastembed's output best, ~0.96 cosine).

Both expose the same `encode(texts, normalize_embeddings) -> (N, dim)` interface.

### Cross-platform vector compatibility

fastembed (INT8 ONNX) and llama.cpp (Q8 GGUF) are different quantizations of the
same nomic weights, so their vectors are **~0.96 cosine-compatible**, not identical.
Each machine is perfectly self-consistent; the small drift only matters if memory
is *synced* across machines running different backends.

---

## Vector-store layer: Qdrant (replacing ChromaDB)

### Why the change

ChromaDB was a poor fit for cross-platform **native** deployment and was the root
cause of the memory system being non-functional off macOS:

- Chroma's server is a Python package whose default embedder is onnxruntime-based
  — the same FreeBSD wall as fastembed.
- Deployment was **Docker** (`docker-compose.yml`; no Docker on FreeBSD) **or** a
  native full-`chromadb` install run via `chroma run`. The "start/stop the DB with
  the app" lifecycle was only ever implemented in `start-macos.sh` — **Linux,
  Windows, and FreeBSD ran with no vector store at all**, silently degrading to
  keyword search.

Qdrant fixes this at the root:

- **Single Rust binary** — no Python server, no onnxruntime, no Docker.
- **Packaged on FreeBSD** (`qdrant` server + `py312-qdrant-client`), so it runs
  natively where Chroma could not.
- **Uniform lifecycle** — the binary is started/stopped with the app on *all*
  platforms, ending the macOS-only asymmetry.
- Higher performance and richer filtering; `qdrant-client` is a thin pure-Python
  client. And **fastembed is Qdrant's own embedding library**, so the embed+store
  pairing is the vendor-matched, officially-supported stack.

### Lifecycle

The Qdrant binary is launched by the app (background process) and reaped on exit —
uniformly across Linux/Windows/macOS/FreeBSD. The app connects via `qdrant-client`
(default `:6333`), overridable with `QDRANT_HOST` / `QDRANT_PORT`.

---

## Status

- **Done & validated:** nomic is the default embedder (`0f14f238`); the
  fastembed→llama.cpp auto-fallback works (host + FreeBSD, `c1101bcd`); the
  install-time verifier recognizes both backends (`c22a0408`).
- **Decided, pending implementation:** the Chroma→Qdrant migration. Scope is a
  bounded backend swap — ~5 core files own the Chroma coupling
  (`src/chroma_client.py`, `embedding_lanes.py`, `memory_vector.py`,
  `rag_vector.py`, plus a few call sites) behind a well-defined collection API
  (create / upsert / search / get / count / delete). **No data migration** is
  needed (memory was never persisting). Plan: a thin `VectorStore` abstraction with
  a Qdrant implementation (allows Chroma coexistence/rollback during transition),
  plus the uniform binary lifecycle. Upstream-candidate; needs its own issue + branch.

## Optimized-nomic details (locked in, implemented with the Qdrant migration)

nomic is run fully rather than like an all-MiniLM drop-in:

- **Matryoshka truncation to 256-dim.** Both embedding backends truncate the 768-dim
  output to its first 256 dimensions and re-normalize (nomic-v1.5 is trained so the
  leading dimensions carry the most signal). 3× smaller vectors and faster search
  for ~1–2% quality cost. Qdrant collections are created at 256-dim. Configurable
  via `EMBEDDING_TRUNCATE_DIM` (default 256).
- **Asymmetric query/document prefixes.** `search_query:` is prepended to queries,
  `search_document:` to documents, at the two encode call sites (which already
  distinguish the two). Applied identically by the fastembed and llama.cpp backends
  so vectors stay aligned across platforms.
- **Chunk size sized for 8K context.** The old `CHUNK_SIZE = 1000` chars (~250
  tokens, in `src/personal_docs.py` / `src/rag_vector.py`) was a fossil of
  all-MiniLM's 256-token limit. Raised to embed whole notes/sections as single
  vectors — the biggest retrieval-coherence win from nomic's long context.
