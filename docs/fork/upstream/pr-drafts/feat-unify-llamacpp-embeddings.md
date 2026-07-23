# PR Draft: feat/unify-llamacpp-embeddings → odysseus-dev/odysseus:dev

**Fork issue:** [#TBD](https://github.com/jdmanring/odysseus/issues) — create before branching
**Branch:** `feat/unify-llamacpp-embeddings` (from `upstream-mirror`)
**Target:** `odysseus-dev/odysseus:dev`
**Status:** Draft — code complete and green on the Linux host; needs the multi-platform install pass before filing

---

## Proposed title

`feat(memory): unify embeddings on llama.cpp (GGUF), retire the onnxruntime backend`

---

## Summary

### Problem

Odysseus is already a **llama.cpp/GGUF-native** application. Local model inference
runs through `llama-server` as a first-class backend, with dedicated integration for
its slot-affinity hints (issue #2927), its `/props` discovery endpoint, its `timings`
block, and `--jinja` handling. GGUF is a format the project already ships and reasons
about throughout the Cookbook/download stack.

Embeddings were the **one exception**. Semantic memory, RAG, and tool selection ran
on **fastembed**, which pulls in **onnxruntime** — an entire second native ML runtime
and a second model format (ONNX), maintained purely to embed. That split cost real
maintenance surface (a body of onnxruntime-specific workarounds, below) and gained
nothing measurable: on the one-item-at-a-time embedding workload the two backends are
equivalent on the axes that matter.

### Solution

Make **llama.cpp (nomic-embed-text-v1.5, Q8_0 GGUF)** the default local embedding
backend on every platform, running the *same* model fastembed did so vectors stay
compatible. fastembed becomes an opt-in alternative
(`EMBEDDING_LOCAL_BACKEND=fastembed`), not a dependency.

`build_local_embed_client()` prefers llama.cpp and falls back to whichever backend is
actually installed, so no existing install loses semantic memory during the
transition. The client is tuned for the two real workloads: `n_threads` (default
`min(4, cores)`) for the per-item hot path — single-item latency is flat past ~4
threads — and `n_threads_batch` (all cores) for the rare full reindex. Context
defaults to the GGUF's true 2048-token train range, with a load-time **YaRN** path
(`LLAMACPP_EMBED_CTX>2048`) for long-document RAG.

### Measured basis for the change

| Axis | fastembed (INT8 ONNX) | llama.cpp (Q8_0 GGUF) | Verdict |
|------|----------------------|-----------------------|---------|
| Per-item latency (the hot path) | few ms | **p50 ~9.5 ms** | equivalent, imperceptible |
| Retrieval accuracy (topic-acc) | identical | identical | quant/backend-independent on this task |
| Bulk throughput (tuned, 24 cores) | **~62 docs/s** | ~37 docs/s | fastembed wins — but bulk only occurs on a one-off reindex |

The single axis fastembed wins (bulk throughput) is exercised only by a full
reindex, which even the slowest backend finishes in minutes and which the memory
workload otherwise never triggers.

---

## The onnxruntime baggage that evaporates

Every item below existed *only* to keep fastembed/onnxruntime working. Retiring the
backend removes all of it (14 workaround sites, grep-verified):

- **Windows MSVC Redistributable requirement** — onnxruntime's `.pyd` links the MSVC
  runtime; without it the DLL load fails. `setup.ps1` installs it; the verifier
  special-cases the error string.
- **~30 lines of broken-symlink cache-healing** in `FastEmbedClient` — HF-hub stores
  the model as symlinks Windows refuses to follow on a UNC/network share
  (`WinError 1463`), silently degrading semantic memory; the code detects the dead
  link and forces a re-download.
- **`HF_HUB_DISABLE_SYMLINKS` module-top env hack**, set before any import so
  onnxruntime can load the model on Windows at all.
- **`py-rust-stemmers` source build on the BSDs** — no wheel, needs the Rust
  toolchain; onnxruntime has no BSD build whatsoever.
- **Arch-mismatch onnxruntime wheel guard** in `setup.py` (pip pulling the wrong-CPU
  binary).
- **The two-backend fallback branching itself** — a fastembed→llama.cpp selection
  path in `embedding_lanes.py` and the install verifier, collapsed to one default
  plus an opt-in.

## What it opens up

fastembed can only run models in its **curated ONNX registry**. llama.cpp runs **any
GGUF**, so the whole community embedding ecosystem becomes reachable by config:

- **Model upgrades are one env var** (`LLAMACPP_EMBED_REPO` / `LLAMACPP_EMBED_FILE`),
  no code change — e.g. the multilingual upgrade path (`nomic-embed-text-v2-moe`,
  `BAAI/bge-m3`, `arctic-embed-v2`). Impossible on fastembed unless that model has
  been ONNX-converted into their registry.
- **Quantization becomes a choice** — f16 / Q8 / Q6 / Q4 per the RAM-vs-quality
  tradeoff, instead of the single quant fastembed shipped.
- **The community quantizer ecosystem** (bartowski, mradermacher, …) — the same
  library the GGUF-discovery work already taps for LLMs now applies to embedders.
- **True 8K context** via the documented YaRN runtime lever — a llama.cpp capability
  fastembed doesn't expose.

---

## Files changed

- `src/embeddings.py`: `build_local_embed_client()` — llama.cpp default with a
  resilient preference chain (fastembed opt-in via `EMBEDDING_LOCAL_BACKEND`);
  `LlamaCppEmbedClient` tuned (`n_threads`/`n_threads_batch` split, `n_ctx` default
  2048, YaRN auto-engaged above 2048); docstrings/module header updated.
- `src/embedding_lanes.py`: `_build_fastembed_client` → `_build_local_lane_client`,
  builds the local backend via `build_local_embed_client()`.
- `requirements.txt`: `llama-cpp-python` (from the prebuilt CPU wheel index via
  `--extra-index-url`) replaces `fastembed`.
- `requirements-optional.txt`: `fastembed` as an opt-in alternative.
- `tooling/verify_memory_stack.py`: checks the llama.cpp default first, recognizes
  fastembed as the alternative.
- `docs/dev/memory-architecture.md`: rationale, baggage, future-opening, YaRN/context
  reality, and multilingual-upgrade guidance.
- `tests/test_embedding_lanes*.py` (5 files): monkeypatch target renamed to
  `_build_local_lane_client`.

## Backward compatibility

- **No data loss on upgrade.** Switching backend flips the lane fingerprint, which
  recreates the memory/RAG collections empty; `app_initializer` already reindexes
  from the canonical memory store on an empty collection at startup, so existing
  users' memories are re-embedded automatically on first launch. (The BSDs were
  already on llama.cpp, so they're unaffected.)
- **No mid-transition regression.** The preference chain keeps an install that still
  has only fastembed healthy until it reinstalls.
- A configured `EMBEDDING_URL` still takes precedence, unchanged.

## Checks run

```bash
# Full suite
python -m pytest -q                      # exit 0, all pass
# Targeted: embedding backend + lanes + vector-client mode selection
python -m pytest tests/test_embedding_lanes*.py tests/test_vector_client_local_mode.py \
                 tests/test_embedding_cache_confinement.py tests/test_fastembed_cache_path.py -q
# Install-time verifier
python tooling/verify_memory_stack.py    # ok, llama.cpp backend loads
```

Measured on the host: per-item Q8 embedding p50 ~9.5 ms; the default 2048 context
loads clean; the `LLAMACPP_EMBED_CTX=8192` YaRN path loads with rope scaling engaged.

## Known upstream-acceptance risk (call out honestly when filing)

This flips the **zero-config install default** from "one clean PyPI fastembed wheel,
~50 MB" to "llama-cpp-python (23 MB wheel) from the CPU wheel index + a ~130 MB GGUF
fetched at first run."

**Wheel coverage is verified, not assumed.** The `--extra-index-url` serves prebuilt
`py3-none` wheels (v0.3.34) for cp310–cp314 across manylinux2014 + musllinux_1_2
(x86_64 and aarch64), macOS (arm64 + x86_64), and win_amd64. Confirmed concretely:
`pip download` on the dev host (Python 3.14, linux x86_64) pulled the prebuilt
`llama_cpp_python-0.3.34-py3-none-manylinux2014_x86_64` wheel — **no compiler
invoked.** A source build happens only on a platform/arch off that index (e.g. the
BSDs, which build from source deliberately via `provision_bsd_memory.sh`).

Residual acceptance risk is therefore modest: it's a heavier *default* (extra index +
larger first-run download), not a compiler requirement for mainstream users. Upstream
may still prefer fastembed's single-index wheel. Lead with the **runtime-unification +
any-GGUF-flexibility** argument (Odysseus is already llama.cpp-native; embeddings were
the last onnxruntime holdout), not speed. If upstream declines, the fork carries it
regardless (it runs BSD and wants the flexibility).

## Checklist

- [ ] I searched [open issues](https://github.com/odysseus-dev/odysseus/issues) and [open PRs](https://github.com/odysseus-dev/odysseus/pulls); this is not a duplicate.
- [x] This PR targets `dev`
- [x] My changes are limited to the scope described above; no unrelated refactors mixed in.
- [ ] I actually ran the app and verified the change works end-to-end on more than the dev host.
- [ ] **I am not an LLM agent submitting a bulk PR.** I reviewed and tested this change personally before submitting.

## Type of Change

- [ ] Bug fix
- [x] New feature (non-breaking; adds a backend default, keeps the old one opt-in)
- [ ] Breaking change
- [x] Refactor / cleanup (retires a redundant dependency stack)
- [ ] Documentation only

## Filing Notes

1. **Create the fork issue first** and record its number above; per fork policy no
   branch exists without an issue.
2. Branch from `upstream-mirror`; cherry-pick to `develop` for the fork.
3. **Before filing, run the install on a non-BSD platform** to confirm the wheel
   index resolves a prebuilt `llama-cpp-python` (and note the fallback-to-source case
   for any Python with no wheel). The "Checks run" above are host-only so far.
4. Coordinate with the GGUF-discovery PR (`feat-gguf-discovery.md`) — both lean on the
   community GGUF ecosystem and the shared quant vocabulary.

## Remaining before "Ready to file"

- Wheel *resolution* is verified (see risk section); still want a real end-to-end
  **app run** on at least one non-BSD platform (import → first embed → memory search)
  before filing, since host checks so far are pytest + a direct backend smoke, not the
  full app.
- (Done) Stale fastembed-framed comments in `setup.sh` / `provision_bsd_memory.sh`
  updated to the unified framing.
