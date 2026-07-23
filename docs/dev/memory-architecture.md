# Memory / RAG architecture

Reference for how embeddings are produced and where vectors are stored.
Numbers current as of 2026-07-24; regenerate them with the two benchmark
tools rather than trusting stale prose (see Benchmarks below).

## The stack

| Layer | All platforms (Linux, Windows, macOS, FreeBSD, OpenBSD) |
|-------|---------------------------------------------------------|
| Embeddings | llama.cpp (nomic GGUF Q8_0) — fastembed opt-in where onnxruntime runs |
| Vector store | Qdrant, app-managed server (embedded local mode as no-binary fallback) |

Embeddings and the vector store are separate concerns. The embedding backend
turns text into vectors; Qdrant stores and searches them. Either can be swapped
without the other caring.

## Embedding layer

### Model: nomic-embed-text-v1.5 (Q8_0 GGUF)

768-dim, 8K-token context, roughly 130 MB quantized, Apache-2.0.

It replaces `all-MiniLM-L6-v2`, which had been the default. all-MiniLM is a 2021
model with a 384-dim output and a 256-token context; nomic brings a far larger
context window (the model supports 8K tokens; the app runs it at 2048, ample
for its 2048-char chunks — MiniLM would truncate those chunks in half),
asymmetric query/document prefix training, and Matryoshka truncation, at a
comparable footprint. On the benchmark's own 12-query corpus both models
score at ceiling (MiniLM top-1 1.000, nomic 0.917 with its one miss at rank
2) — that corpus proves the backend and quantization choices don't degrade
retrieval, not that either model beats the other; the retrieval-quality case
for nomic rests on the properties above and on published MTEB retrieval
scores.

qwen3-embedding was considered and rejected. It isn't fastembed-supported (it's
decoder-based, not BERT-style), it's 4-5x heavier (595M vs 137M params), and its
advantages (multilingual coverage, 32K context) don't buy anything for a
single-user English workspace.

### Backend selection: llama.cpp everywhere, fastembed opt-in

`LlamaCppEmbedClient` (llama.cpp via `llama-cpp-python`, running the nomic GGUF
with mean pooling and L2 normalization) is the default on every platform. One
backend everywhere means one provisioning story and no cross-backend vector
drift; it is also the only option on the BSDs, where fastembed's onnxruntime
runtime has no Python binding at all (the port ships the C++ library only —
this wall is what originally forced the backend decision).

**Before/after, measured.** The benchmark runs the replaced model
(`all-MiniLM-L6-v2`, at its native 384 dims) alongside both nomic backends on
two corpora. On the easy topic corpus both models sit at ceiling (MiniLM
top-1 1.000, nomic 0.917 with its one miss at rank 2) — that tier proves the
backend and quantization choices don't degrade retrieval, nothing more. The
hard tier is memory-shaped and built to separate models, scored against one
pooled 122-doc index (41 scored queries plus 40 background filler memories,
so every stored memory is a ranking distractor). Five sections: polysemy
traps, stale-vs-current facts, numeric binding, relational binding, and
consolidated-note documents at production chunk size with the queried fact
past MiniLM's 256-token window. Results, deterministic per backend: nomic
0.805 (fastembed INT8) / 0.756 (llama.cpp Q8) overall with long-doc recall
5/6; all-MiniLM 0.683 with long-doc recall 1/6. The long-doc column makes
the truncation argument structural: a 256-token model cannot retrieve a
fact it never embedded, and this app's chunks are ~512 tokens. Two honest
notes travel with the numbers: the stale section defeats every model
roughly equally — ranking current facts above outdated ones is the memory
layer's supersede logic's job, not retrieval's — and the two nomic quants
differ by ~2 items at the hard margin, so they are backend-equivalent
within noise rather than identical.

fastembed (ONNX INT8) remains available as an opt-in
(`EMBEDDING_LOCAL_BACKEND=fastembed`, dependency in `requirements-optional.txt`)
where onnxruntime runs. Measured per-item (query embed p50, idle machines, two
consistent passes): the two backends are within ~1 ms of each other everywhere
— llama.cpp slightly ahead on Linux/Windows/FreeBSD with a native build,
fastembed ~1 ms ahead on x86 macOS (3.9 vs 5.0 ms) and on OpenBSD. Retrieval
accuracy is identical (top-1 0.917 / top-3 1.000 on the benchmark corpus, 10/12
top-1 agreement): the choice is operational, not qualitative. fastembed's real
advantage is bulk throughput (~2x, ~310 vs ~140-190 docs/s), which only matters
on a one-off full reindex.

Both backends expose the same `encode(texts, normalize_embeddings, is_query)`
signature and apply the same nomic prefixes and Matryoshka truncation via
shared helpers, so vectors line up regardless of which produced them.

### Native builds and per-platform latency

The prebuilt `llama-cpp-python` wheels target a generic AVX2 baseline. A native
source build (`GGML_NATIVE`, `-march=native`) uses the host's full SIMD —
AVX-512 VNNI drives the Q8_0 dot products — and measurably beats both the wheel
and fastembed on the per-item hot path. Representative numbers (single query
embed, p50, idle machines, two consistent passes): ~4.9 ms on a bare-metal
Zen 4 Linux host; 5.0-5.9 ms in 12-vCPU VMs of Windows (Clang+Ninja+OpenMP —
MSVC's `GGML_NATIVE` is a no-op and explicit AVX-512 under MSVC is a measured
regression), FreeBSD, and x86 macOS (patched-sdist build, Accelerate/BLAS off —
BLAS costs ~30% bulk on quantized models); ~7 ms on OpenBSD, whose hardened
malloc accounts for 0.5-2.5 ms of that (measured by `MALLOC_OPTIONS` A/B and
deliberately NOT relaxed — weakening malloc hardening is antithetical to
running OpenBSD; the number is recorded as the explanation of the gap, not as
a tuning option). The spread is a stack of priced costs — virtualization,
platform feature masks, security hardening — not backend variance.

### Threading: the batch pool is capped for a reason

`n_threads` (default `min(4, cores)`) serves single-item calls; `n_threads_batch`
(default `min(8, cores)`; `min(4, cores)` on OpenBSD; override
`LLAMACPP_EMBED_THREADS_BATCH`) serves batch calls. The cap matters: llama.cpp
selects the batch pool for any multi-*token* call — which is every query
embed — and an oversized spinning thread team per process degrades or
collapses under multi-process traffic, and the app plus the memory MCP
subprocess is exactly a two-process topology. Measured, two concurrent
processes, capped vs uncapped (all-cores) pool:

- 24-core Linux host (libgomp): 4.9 ms → 1.3 s uncapped (260x); capped, solo
  latency is unchanged (5.0 vs 4.9 ms), bulk −15%, and 4-process contention
  degrades gracefully (bare embeds ~7-10 ms; full memory searches p50
  ~20-30 ms).
- 12-vCPU FreeBSD guest (libomp): 6.3/6.6 ms capped vs 17-25 ms uncapped.
- 12-vCPU Windows guest (LLVM libomp): 9.7/10.6 ms capped vs 11.7/13.8
  uncapped — mildest case; LLVM's runtime spins less aggressively.
- 12-vCPU OpenBSD guest (no OpenMP — ggml's own spin threadpool): the
  pathological case. Two 8-thread pools oversubscribing 12 vCPUs livelock the
  scheduler with deterministic ~35 s stalls per embed; at 2x4 threads it runs
  at a clean 13 ms. Hence the harder OpenBSD cap of 4, which costs ~4 ms solo
  (7.5 → 11.7 ms) and buys a working two-process topology.

Raise the env override for a one-off bulk reindex if the throughput cap ever
matters.

### Cross-platform vector compatibility

fastembed (INT8 ONNX) and llama.cpp (Q8 GGUF) are different quantizations of the
same nomic weights, so their vectors are about 0.96 cosine-compatible rather than
bit-identical. Each machine is self-consistent; per-lane embedding fingerprints
(see Lifecycle) force a clean reindex when a machine's backend changes.

## Vector-store layer: Qdrant (replacing ChromaDB)

### Why the change

The migration started from a concrete need: a vector store that runs on FreeBSD.
ChromaDB does not. Its server is a Python package whose default embedder is
onnxruntime-based, and onnxruntime has no FreeBSD Python binding — the same wall
fastembed hits. There is no native FreeBSD deployment path for it.

Qdrant answers that need directly. It is a single Rust binary — no Python server,
no onnxruntime, no Docker — and FreeBSD packages it (`qdrant` server plus
`py312-qdrant-client`), so it runs natively where Chroma cannot. `qdrant-client`
is a thin pure-Python client.

That pointed to a fleet-wide upgrade rather than a FreeBSD-only patch:
adopt the same store everywhere, including that start/stop-with-the-app lifecycle
on every platform.

### Lifecycle: app-managed server by default

`src/qdrant_server.py` launches the pinned Qdrant binary as a background process
on startup and reaps it on exit; `src/vector_client.py` connects to it
(`QDRANT_PORT`, default 6333). The embedded in-process store (`QdrantClient(path=...)`)
remains only as a fallback when no server binary can be resolved, or forced via
`QDRANT_EMBEDDED=1` for deliberate single-process deployments and tests. Set
`QDRANT_HOST` to use an external server instead (the docker-compose deployment
does exactly this with the official Qdrant image).

The binary is resolved from `QDRANT_BIN`, then `PATH` (FreeBSD and OpenBSD
package or build it; on other platforms install the official static release or
point `QDRANT_BIN` at it). Without a binary the app still runs — vectors land
in the embedded store — but that store is single-process: a second process
such as the memory MCP server cannot open it, and its memory features degrade
until a server is available. The degradation is logged at startup.

The server exists for one reason: the embedded store takes an exclusive storage
lock — one process, period — and the app is not one process (the memory MCP
server is a separate OS process sharing the same collections). There is no
shared-file concurrent mode in Qdrant; routing all consumers through a single
owning process over IPC would just be a hand-rolled, worse server.

**The server's price is measured, not assumed** (one process, n=100, two passes,
`tooling/benchmark_memory_store.py`): search end-to-end p50 6.1/6.4 ms against
the server vs 5.3/5.4 ms embedded — about **0.9 ms per search** (an in-process
store call is ~0.1 ms; the localhost HTTP query is ~1.0 ms). `add()` runs
~9.5 ms vs ~8 ms. Decomposed, an end-to-end memory search is: query embed
(~5 ms, the dominant term everywhere) + one Qdrant query (~1 ms) + under 0.5 ms
of adapter — so platform-to-platform differences in search latency track the
embedder, not the store.

Search-path discipline that keeps it this fast: `MemoryVectorStore.search()`
performs no `count()` pre-flight checks. Each one is an HTTP round-trip in
server mode (~10 ms of pure overhead per search when they were present — free
under the embedded store, which is how they went unnoticed), and Qdrant simply
returns fewer or zero hits when `limit` exceeds the stored points, so the
guards defended nothing. A regression test asserts search makes zero `count()`
calls.

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
`EMBEDDING_TRUNCATE_DIM` (default 256) tunes it. Measured (dim sweep in the
backend benchmark, `BENCH_DIM_SWEEP=1`): top-1 accuracy is flat from 64 through
512 dims on the benchmark corpus, and the mean top1-vs-top2 similarity margin
peaks exactly at 256 — the default keeps the best separation the sweep found
while paying a third of the full vector cost.

**Asymmetric query/document prefixes.** Queries get `search_query:`, stored
documents get `search_document:`, applied at every encode call site that
distinguishes the two — including `MemoryVectorStore.search()`. nomic is
trained on exactly this split, and it measurably sharpens retrieval. Both
backends apply the prefixes identically so vectors stay aligned across
platforms. (`find_similar()` deliberately does *not* prefix: it is a
document-to-document duplicate check.)

**Chunk size tuned to nomic, not maxed to its context.** The old `CHUNK_SIZE = 1000`
chars (about 250 tokens, in `src/personal_docs.py` and `src/rag_vector.py`) was a
leftover from all-MiniLM's 256-token limit. It's now 2048 chars, roughly 512 tokens,
with 300 chars of overlap. The point is deliberately *not* to fill nomic's 8K
context per chunk: a large chunk averages many sentences into one vector and dilutes
what the vector points at, so retrieval gets worse, not better. ~512 tokens is the
sweet spot between capturing enough context and keeping each vector about one idea.

## Benchmarks and verification

Two tools regenerate every number in this document; both refuse to run under
conditions that would fake the result:

- `tooling/benchmark_embedding_backends.py` — backend comparison: retrieval
  accuracy on a topic-labelled paraphrase corpus, query-embed latency
  (n=100, p50/p95/p99/max), and bulk throughput (median of 5 with spread).
  Refuses to run on a loaded host (`BENCH_FORCE=1` overrides): these are
  CPU-bound measurements and background load inflates them 100x.
- `tooling/benchmark_memory_store.py` — the store end to end: `add()` latency,
  search e2e distribution, in-process embed/store/adapter decomposition,
  server-vs-embedded A/B, and a multi-process contention probe whose workers
  barrier-synchronize past model load (so it measures steady state, not
  startup interference). Refuses to run against a store that already holds
  vectors — a leftover server on the port silently turns `add()` into
  duplicate-skips and fakes sub-millisecond writes.

`tooling/verify_memory_integration.py` is the correctness gate: four phases
(server-mode assertion, real write/search through llama.cpp with a paraphrase
query, a concurrent second OS process on the same collections, and restart
persistence) against a dedicated port and data dir. Run it after any change to
the store, the server lifecycle, or the embedding layer.

Measurement discipline for any number that lands in this file: idle machine
(verify, don't assume — post-boot scanner processes gone, not just low load
average), one machine under test at a time, two consistent passes.

## Status

Done and validated:

- llama.cpp (nomic GGUF Q8_0) is the default embedder on every platform;
  fastembed is opt-in where onnxruntime runs.
- Optimized nomic: 256-dim Matryoshka truncation, query/document prefixes, and the
  2048-char chunk size, applied identically by both backends.
- The Chroma-to-Qdrant store swap. `src/vector_client.py` is a
  Chroma-shaped adapter over `QdrantClient`; the six Chroma call sites moved onto
  it and ChromaDB was removed outright (no data to migrate — nothing persisted).
  The adapter converts Qdrant's similarity score back to a Chroma-style cosine
  distance, maps arbitrary string IDs to UUIDs, and translates `where=` equality
  filters.
- The app-managed Qdrant server lifecycle (`src/qdrant_server.py`), integration-
  verified end to end on Linux, Windows, macOS, FreeBSD, and OpenBSD via
  `tooling/verify_memory_integration.py`.
- The multi-process embedding thread cap (see Threading above).
- Benchmark tooling with contamination guards (see Benchmarks above).
