# Memory / RAG architecture

Reference for how embeddings are produced and where vectors are stored across the
fleet. Locked in 2026-07-22.

## The stack

| Layer | All platforms (Linux / Windows / macOS / FreeBSD / OpenBSD) |
|-------|-------------------------------------------------------------|
| Embeddings | llama.cpp (nomic GGUF Q8_0) — fastembed opt-in via `EMBEDDING_LOCAL_BACKEND=fastembed` |
| Vector store | Qdrant (native package on the BSDs) |

Embeddings and the vector store are separate concerns. The embedding backend turns
text into vectors; Qdrant stores and searches them. The backend can differ per
platform without the store caring, which is what lets FreeBSD swap ONNX for GGUF
while everything downstream stays identical.

## Embedding layer

### Model: nomic-embed-text-v1.5 (Q8_0 GGUF on llama.cpp)

768-dim (truncated to 256, see below), roughly 130 MB at Q8_0, Apache-2.0.

Context note: nomic-v1.5 advertises an 8K context, but that relies on **Dynamic
NTK-Aware RoPE**, which llama.cpp doesn't implement — so every GGUF (nomic's own
included) reports `n_ctx_train=2048`, and there is no "properly converted" 8K GGUF to
find, from any quantizer. 8K is reachable only as a **load-time YaRN substitute**
(`n_ctx=8192`, `rope_scaling_type=yarn`, `rope_freq_scale=0.75` — nomic's documented
recipe). We default to 2048 (`LLAMACPP_EMBED_CTX`) because memory entries and RAG
chunks are far shorter; the naive `n_ctx=8192` without YaRN doesn't extend context,
it just runs inputs past the trained range and degrades them. Raise it with YaRN only
if RAG needs to embed genuinely long documents in one vector.

It replaces `all-MiniLM-L6-v2`, which had been the default. all-MiniLM is a 2021
model with a 384-dim output and a 256-token context; nomic gives meaningfully better
retrieval and a 32x larger context window at a comparable footprint, and it is
trained for the asymmetric query/document prefixing we now use.

qwen3-embedding was considered and rejected. It isn't fastembed-supported (it's
decoder-based, not BERT-style), it's 4-5x heavier (595M vs 137M params), and its
advantages (multilingual coverage, 32K context) don't buy anything for a
single-user English workspace.

### Backend selection

**llama.cpp (GGUF Q8_0) is the local default on every platform.** A configured HTTP
endpoint (`EMBEDDING_URL`) still wins when present; absent that,
`src/embeddings.py::build_local_embed_client()` builds `LlamaCppEmbedClient`, and
`src/embedding_lanes.py::_build_local_lane_client()` does the same for the lane.

The fleet used to split — fastembed (ONNX) on Linux/Windows/macOS, llama.cpp only on
the BSDs (onnxruntime has no BSD binding). We unified on llama.cpp because the split
bought nothing and cost maintenance:

- **Per-item latency — the actual hot path (every RAG query, memory search, and
  tool-selection embeds one item) — is a wash:** ~6 ms fastembed vs ~7 ms llama.cpp
  Q8. Both imperceptible.
- fastembed's *only* real advantage is **bulk throughput** (~240 vs ~136 docs/s
  batched). But bulk only happens on a one-off full reindex, where even the slower
  backend finishes a few thousand memories in seconds — the memory workload
  otherwise embeds one item at a time.
- **Retrieval accuracy is quant- and backend-independent** on this task: on a
  30-doc / 12-query paraphrase set, fastembed INT8 and llama.cpp Q8 scored the
  *identical* top-1 0.917 / top-3 1.000 and agreed on 10/12 queries.

All three figures are reproducible on demand — run
`tooling/benchmark_embedding_backends.py` (it builds a topic-labelled corpus and
compares both backends on accuracy, per-item latency, and bulk throughput).
**Measure on an idle host:** these are CPU-bound with OpenMP threads, so a
competing load (e.g. a VM compiling in the background) inflates per-item latency by
100× and makes the comparison meaningless — a lesson learned the hard way here.
- One backend means one provisioning story (no onnxruntime wheel-hunting) and no
  cross-backend vector drift.

**Odysseus is already a llama.cpp/GGUF-native app; embeddings were the lone
exception.** Local LLM inference already runs through `llama-server` as a first-class
backend — the codebase carries dedicated integration for its slot-affinity hints
(issue #2927), its `/props` discovery endpoint, its `timings` block, and its
`--jinja` handling. GGUF is a format the project already ships and reasons about.
fastembed was the *one* feature dragging in a whole **second** native ML stack —
onnxruntime, the ONNX model format, and their own tokenizer/stemmer dependencies —
purely to embed. Unifying on llama.cpp means one local-ML engine and one model format
end to end. (The binding added here, `llama-cpp-python`, is a distinct pip artifact
from the `llama-server` binary the app talks to over HTTP: same engine, same GGUF
format, same platform knowledge, different interface. Serving embeddings from a
`llama-server` `/v1/embeddings` endpoint via the existing `EMBEDDING_URL` path is the
even-tighter option for anyone who'd rather run a server than load the model
in-process.)

**The onnxruntime baggage that evaporates.** Everything below existed *only* to keep
fastembed/onnxruntime working, and is now dead weight the fork sheds — grep-verified,
14 workaround sites across the tree:

- The Windows **MSVC Redistributable** requirement — onnxruntime's `.pyd` links the
  MSVC runtime; without it the DLL load fails (`setup.ps1` installs it; the verifier
  special-cases the error).
- **~30 lines of broken-symlink cache-healing** in `FastEmbedClient` — the HF-hub
  cache stores the model as symlinks that Windows on a UNC/network share refuses to
  follow (`WinError 1463`), silently degrading semantic memory; the code detects the
  dead link and forces a re-download.
- The module-top **`HF_HUB_DISABLE_SYMLINKS`** env hack, set before any import so
  onnxruntime can load the model at all on Windows.
- On the BSDs, fastembed's **`py-rust-stemmers`** dependency has no wheel and needs
  the Rust toolchain to compile; onnxruntime has no BSD build at all.
- **Arch-mismatch onnxruntime wheels** (`setup.py` guards against pip pulling the
  wrong-CPU binary).
- The **fastembed→llama.cpp fallback branching** itself — a two-backend selection
  path in `embedding_lanes.py` and the verifier, now a single default with an opt-in.

**What it opens up (the future the fork gains).** fastembed can only run models in its
**curated ONNX registry**; llama.cpp runs **any GGUF**, so the whole community
embedding-model ecosystem becomes reachable by changing an env var:

- **Model upgrades are one line.** The multilingual path documented below
  (`nomic-embed-text-v2-moe`, `bge-m3`, `arctic-embed-v2`) is `LLAMACPP_EMBED_REPO` /
  `LLAMACPP_EMBED_FILE`, no code change — impossible on fastembed unless they happen
  to have ONNX-converted that model.
- **Quant is a choice, not a given.** f16 / Q8 / Q6 / Q4 per the RAM-vs-quality
  tradeoff, instead of whatever single quant fastembed shipped.
- **The community quantizer ecosystem is in reach** (bartowski, mradermacher, …) —
  the same library the fork's GGUF-discovery work already taps for LLMs now applies
  to embedders too.
- **True 8K context** via the load-time YaRN path (see the model note above) — a
  llama.cpp runtime lever fastembed doesn't expose.

`LlamaCppEmbedClient` runs nomic-embed-text-v1.5 as a Q8_0 GGUF via
`llama-cpp-python`, mean pooling + L2 normalization, with two thread configs:
`n_threads` (default min(4, cores)) drives the per-item hot path — single-item
latency is flat past ~4 threads — while `n_threads_batch` (default all cores) drives
the rare bulk reindex. fastembed stays reachable for a one-off via
`EMBEDDING_LOCAL_BACKEND=fastembed`. Both expose the same
`encode(texts, normalize_embeddings) -> (N, dim)` signature and apply the same nomic
prefixes + Matryoshka truncation, so vectors line up regardless of backend.

### Why in-process, not an app-managed llama-server (decided, don't re-litigate)

The default local backend loads the GGUF **in-process** via `llama-cpp-python`, rather
than the app spawning and lifecycle-managing a `llama-server` to embed against over
HTTP. The decision rule is *does centralizing solve a correctness or heavy-resource
problem worth a server lifecycle?* — and embeddings trigger neither:

- **Qdrant is a server** because it holds shared *mutable state* behind a single-writer
  lock (the app and the memory MCP subprocess collide on the embedded store) — a
  correctness requirement.
- **The LLM is a server** because the generation model is a *heavy shared resource*
  (large, often GPU-resident, loaded once and shared).
- **Embeddings are neither** — a stateless pure function (text→vector, no lock, each
  process can hold its own copy) over a small CPU model (~130 MB). Centralizing buys
  nothing you'd pay lifecycle cost for, and an always-on embedding server would
  re-introduce exactly the port/orphan/shutdown handling `qdrant_server.py` already
  carries, plus a localhost round-trip per ~7 ms embed.

Anyone who *does* want to serve embeddings (out-of-process isolation, a shared
llama-server on a multi-client host) already can: set `EMBEDDING_URL` to any
OpenAI-compatible endpoint — including their own `llama-server` `/v1/embeddings` — and
it takes precedence over the in-process backend. So both options exist; only the simple
one is maintained.

### If multilingual retrieval is ever needed: upgrade the model

The whole analysis above assumes an **English (or English-dominant) workspace**,
where nomic-embed-text-v1.5 is the right call — small, fast, and retrieval quality
that a bigger model won't measurably beat on English memory/RAG. That assumption is
the hinge. If memories or RAG documents are stored and searched in **other
languages**, v1.5 is the wrong tool (it's English-centric) and the fix is a *model*
upgrade, not a quant or context tweak.

Recommended multilingual upgrade: **`nomic-ai/nomic-embed-text-v2-moe`**. It is the
best *fit* for this architecture, not just a leaderboard name:

- SOTA multilingual retrieval (~100 languages) at its size class — competitive with
  models 2× larger — which is exactly the axis v1.5 is weak on.
- Same nomic family: same `search_query:` / `search_document:` prefixes and Matryoshka
  768→256, so it slots into the existing prefix + 256-dim pipeline with **no lane or
  code change** — only the `LLAMACPP_EMBED_REPO` / `LLAMACPP_EMBED_FILE` env vars
  (point them at `nomic-ai/nomic-embed-text-v2-moe-GGUF`).
- Merged llama.cpp support ([ggml-org/llama.cpp#12466](https://github.com/ggml-org/llama.cpp/pull/12466)),
  official GGUF, HF-parity to ~6e-7 MSE — so it runs in the same unified llama.cpp
  path on every platform.

Cost of the upgrade, to weigh consciously: ~305M MoE params vs v1.5's ~137M — higher
RAM (MoE keeps all experts resident) and somewhat slower per-item embeds. Switching
backend/model changes the lane fingerprint, triggering a one-time reindex from the
canonical memory store (automatic; see Lifecycle). **Only take this on if
multilingual is a real requirement** — on English it's a lateral move at higher cost.

Alternative if maximum multilingual quality matters more than fit: `BAAI/bge-m3`
(strong multilingual, native 8192 context) — but it's larger, fixed 1024-dim (a lane
dimension change, not a drop-in), and uses different prefixing. Prefer v2-moe unless
a benchmark on your actual multilingual data justifies the heavier switch.

Whichever is chosen, decide it with a retrieval benchmark on **multilingual** pairs
(where the gain actually shows), not English — on English our own benchmark is flat
across models and would hide the difference.

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

The default is an **app-managed Qdrant server** (`src/qdrant_server.py`, launched
lazily by `get_vector_client()` in `src/vector_client.py`): the app resolves a
`qdrant` binary (PATH first — FreeBSD pkg / OpenBSD source build — then
`BinManager` on Linux/macOS/Windows), starts it on `127.0.0.1:6333` with storage
under `DATA_DIR/qdrant`, and waits on `/readyz`. `ensure_running()` is idempotent
across processes — if something already answers on the port, it just connects —
so the memory MCP subprocess attaches to the server the app started instead of
launching a rival, and only the process that spawned the child stops it.

Setting `QDRANT_HOST` (with optional `QDRANT_PORT`, default 6333) skips the
managed launch and connects to an external Qdrant — the path for a shared/remote
instance. `QDRANT_EMBEDDED=1` forces the embedded store for deliberate
single-process deployments and tests.

**Fallback — embedded local mode.** Where no server binary resolves (e.g. OpenBSD
without the source build), the client falls back to
`QdrantClient(path=DATA_DIR/qdrant)`, the in-process single-writer store. Its
*exclusive cross-process* lock is why server mode is the default: the app process
and the memory MCP subprocess both build a `MemoryVectorStore`, and under the
embedded store the lock's loser silently degrades to keyword memory
(`MemoryVectorStore.healthy`), leaving one of {UI memory routes, LLM memory tools}
without vector search, nondeterministically. Under server mode both processes
share the one server — proven directly by phase C of
`tooling/verify_memory_integration.py` (a second OS process writing and searching
the same collection with the first client open). On a crash the embedded lock is
released with the process (verified: a SIGKILLed holder does not block the next
start).

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
with 300 chars of overlap. The point is deliberately *not* to fill the model's
context per chunk: a large chunk averages many sentences into one vector and dilutes
what the vector points at, so retrieval gets worse, not better. ~512 tokens is the
sweet spot between capturing enough context and keeping each vector about one idea.

## Status

Done and validated:

- nomic (Q8_0 GGUF on llama.cpp) is the default embedder on every platform;
  fastembed is opt-in via `EMBEDDING_LOCAL_BACKEND=fastembed`.
- Per-item latency reproduced on an idle host (`tooling/benchmark_embedding_backends.py`):
  ~6 ms fastembed / ~7 ms llama.cpp Q8 — a wash, both imperceptible, which is what
  justifies dropping the fastembed split. Identical accuracy (top-1 0.917 / top-3
  1.000, 10/12 agreement). (Benchmark under load and the CPU-bound OpenMP path
  inflates llama.cpp ~100×; the tool now refuses to run at load >2 unless forced.)
- The install-time verifier recognizes both backends.
- **The app-managed Qdrant server is the default** (see Lifecycle), with the
  embedded single-writer store only as a fallback where no binary resolves.
  Full-stack integration is verified by `tooling/verify_memory_integration.py`
  (server-mode assertion, real llama.cpp write/search, concurrent second-process
  access, restart persistence) — green on the Linux host and on OpenBSD
  (2026-07-23; see `docs/fork/runbooks/openbsd-qdrant-build.md`). macOS and
  Windows use the same path but were not booted to prove it.
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

- **Single-writer under the embedded fallback (see Lifecycle).** RESOLVED in the
  default configuration: the app-managed Qdrant server lets the app process and
  the memory MCP subprocess share one concurrent store (verified end to end by
  `tooling/verify_memory_integration.py`, including on OpenBSD via the source
  build). The contention now exists only where the embedded fallback is actually
  in use — a host with no resolvable server binary. For that residual case the
  single-owner/proxy design (the MCP server routing vector ops through the app's
  memory API) remains the candidate fix. Tracked under its own issue and branch
  (#161).
