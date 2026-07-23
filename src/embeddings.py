"""
embeddings.py

Embedding clients for RAG and memory vector search.

Priority order:
  1. HTTP API (Ollama / vLLM / llama.cpp) — set EMBEDDING_URL in .env
  2. Local llama.cpp (GGUF Q8_0) — zero-config fallback, runs the nomic model on
     every platform. Set EMBEDDING_LOCAL_BACKEND=fastembed to use fastembed (ONNX)
     instead where it's available; fastembed only wins bulk throughput, which the
     one-at-a-time memory workload never exercises.

Set EMBEDDING_URL in .env, e.g.:
  EMBEDDING_URL=http://localhost:11434/v1/embeddings   (ollama)
  EMBEDDING_URL=http://localhost:8000/v1/embeddings    (vllm / llama.cpp)
"""

import os
import time

from src.constants import FASTEMBED_CACHE_DIR, EMBEDDING_ENDPOINT_FILE

# Windows: force HuggingFace/fastembed to COPY model files rather than symlink
# them. On a network-share/UNC cache dir Windows can't follow HF's symlinks
# ([WinError 1463] "symbolic link cannot be followed"), so ONNX fails to load the
# model and semantic memory dies. huggingface_hub reads this flag at import time,
# so it must be set before huggingface_hub is first imported — hence module-top.
# (app.py sets the same guard for the server entrypoint.)
if os.name == "nt":
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

import structlog
import numpy as np
import httpx
from typing import List, Optional

from src.runtime_paths import get_app_root

logger = structlog.get_logger(__name__)

# nomic-embed-text-v1.5-Q: nomic's official INT8-quantized ONNX (130 MB, near-
# lossless), 768-dim, 8K context — a quality + long-context upgrade over
# all-MiniLM at a comparable footprint. "-Q" is the fastembed-supported quant;
# the HTTP-endpoint default uses the Ollama tag for the same model.
_DEFAULT_MODEL = "nomic-embed-text"
_DEFAULT_FASTEMBED_MODEL = "nomic-ai/nomic-embed-text-v1.5-Q"

# Optimized-nomic knobs (see docs/dev/memory-architecture.md). Matryoshka:
# nomic-v1.5's leading dims carry the most signal, so we truncate 768 -> 256 and
# re-normalize (3x smaller/faster, ~1-2% quality). Prefixes: nomic is trained with
# asymmetric search_query:/search_document: — applied explicitly so both the
# fastembed and llama.cpp backends produce aligned vectors.
_TRUNCATE_DIM = int(os.getenv("EMBEDDING_TRUNCATE_DIM", "256"))
_NOMIC_QUERY_PREFIX = "search_query: "
_NOMIC_DOC_PREFIX = "search_document: "


def _prefix_texts(texts, is_query: bool, model: str):
    """Prepend nomic's task prefix. No-op for non-nomic models."""
    if "nomic" not in (model or "").lower():
        return list(texts)
    p = _NOMIC_QUERY_PREFIX if is_query else _NOMIC_DOC_PREFIX
    return [p + t for t in texts]


def _truncate_and_normalize(vecs, normalize: bool):
    """Matryoshka-truncate to _TRUNCATE_DIM, then (optionally) L2-normalize."""
    if _TRUNCATE_DIM and vecs.ndim == 2 and vecs.shape[1] > _TRUNCATE_DIM:
        vecs = vecs[:, :_TRUNCATE_DIM]
    if normalize and vecs.size > 0:
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)
        vecs = vecs / norms
    return vecs


class EmbeddingClient:
    """Drop-in replacement for SentenceTransformer.encode() using an HTTP API."""

    def __init__(self, url: Optional[str] = None, model: Optional[str] = None, api_key: Optional[str] = None):
        self.url = url or os.getenv(
            "EMBEDDING_URL",
            f"http://{os.getenv('LLM_HOST', 'localhost')}:11434/v1/embeddings",
        )
        self.model = model or os.getenv("EMBEDDING_MODEL", _DEFAULT_MODEL)
        self.api_key = api_key or os.getenv("EMBEDDING_API_KEY")
        self._dim: Optional[int] = None
        # Short connect timeout so a DOWN embedding endpoint (e.g. Ollama not
        # running on :11434) fast-fails to the local FastEmbed fallback instead
        # of stalling startup ~30s per probe. Read stays generous for a real
        # endpoint (embedding a short string returns in well under a second).
        self._client = httpx.Client(timeout=httpx.Timeout(connect=3.0, read=10.0, write=5.0, pool=3.0))
        self._batch_size = max(1, int(os.getenv("EMBEDDING_BATCH_SIZE", "8")))
        self._max_chars = max(200, int(os.getenv("EMBEDDING_MAX_CHARS", "900")))

    def get_sentence_embedding_dimension(self) -> int:
        """Probe the endpoint for embedding dimension if not yet known."""
        if self._dim is not None:
            return self._dim
        # Embed a single word to discover the dimension
        vec = self.encode(["hello"])
        self._dim = vec.shape[1]
        logger.info(f"Embedding dimension: {self._dim} (model={self.model})")
        return self._dim

    def encode(
        self, texts: List[str], normalize_embeddings: bool = True,
        is_query: bool = False,
    ) -> np.ndarray:
        """Encode texts via the API. Returns (N, dim) float32 array. is_query is
        accepted for interface parity; a custom endpoint owns its own model, so no
        nomic prefix/truncation is applied here."""
        if not texts:
            return np.array([], dtype="float32")

        _enc_start = time.monotonic()
        all_vecs = []
        n_batches = 0
        for i in range(0, len(texts), self._batch_size):
            batch = texts[i : i + self._batch_size]
            all_vecs.extend(self._embed_batch(batch))
            n_batches += 1

        vecs = np.array(all_vecs, dtype="float32")

        if normalize_embeddings and vecs.size > 0:
            norms = np.linalg.norm(vecs, axis=1, keepdims=True)
            norms = np.where(norms == 0, 1, norms)
            vecs = vecs / norms

        if self._dim is None and vecs.size > 0:
            self._dim = vecs.shape[1]

        _enc_ms = (time.monotonic() - _enc_start) * 1000
        if _enc_ms > 500 or len(texts) > 128:
            logger.info("embedding_encode", texts=len(texts), batches=n_batches,
                        duration_ms=round(_enc_ms, 1), model=self.model)

        return vecs

    def _embed_batch(self, batch: List[str]) -> List[List[float]]:
        try:
            return self._post_embeddings(batch)
        except httpx.HTTPStatusError as e:
            status = e.response.status_code if e.response is not None else None
            if status != 400:
                raise
            if len(batch) > 1:
                vecs = []
                for text in batch:
                    vecs.extend(self._embed_batch([text]))
                return vecs
            text = batch[0]
            trimmed = text[: self._max_chars]
            if trimmed != text:
                logger.warning(
                    "Embedding input exceeded endpoint context; retrying with %d chars",
                    len(trimmed),
                )
                return self._post_embeddings([trimmed])
            raise

    def _post_embeddings(self, batch: List[str]) -> List[List[float]]:
        resp = self._client.post(
            self.url,
            headers={"Authorization": f"Bearer {self.api_key}"} if self.api_key else {},
            json={"input": batch, "model": self.model},
        )
        resp.raise_for_status()
        data = resp.json()

        # OpenAI format: {"data": [{"embedding": [...], "index": 0}, ...]}
        embeddings = data.get("data", [])
        embeddings.sort(key=lambda e: e.get("index", 0))
        return [emb["embedding"] for emb in embeddings]


class FastEmbedClient:
    """Local embedding client using fastembed (ONNX). No external service needed."""

    def __init__(self, model: Optional[str] = None):
        try:
            from fastembed import TextEmbedding
        except ImportError as e:
            raise RuntimeError(
                "Local fastembed is not installed. Either install it "
                "(pip install fastembed) or point the app at a remote "
                "embeddings server."
            ) from e

        self.model = model or os.getenv("FASTEMBED_MODEL", _DEFAULT_FASTEMBED_MODEL)
        # Persistent cache under data/ so the model survives reboots and so
        # the download lands exactly where the admin panel's _is_downloaded()
        # check looks (both default to this same path).
        cache_dir = FASTEMBED_CACHE_DIR
        os.makedirs(cache_dir, exist_ok=True)
        # Windows self-heal: the HuggingFace-hub cache stores model files as
        # symlinks (snapshots/<rev>/model.onnx -> ../../blobs/<hash>). On a
        # network-share / UNC data dir Windows refuses to follow them
        # ([WinError 1463] "symbolic link cannot be followed because its type is
        # disabled"), and a cache copied between machines can carry dead symlinks
        # too. Either way fastembed tries to load a broken symlink and fails
        # *without* re-downloading, leaving semantic memory degraded. Detect a
        # broken-symlink model in the cache and drop the contaminated hub dir so
        # fastembed re-fetches (it falls back to its CDN tarball of real files,
        # which load fine). Best-effort; only ever removes a verifiably dead link.
        if os.name == "nt":
            try:
                import glob, shutil
                for _onnx in glob.glob(os.path.join(cache_dir, "**", "*.onnx"), recursive=True):
                    if os.path.islink(_onnx) and not os.path.exists(_onnx):
                        _root = _onnx
                        while os.path.basename(_root) and not os.path.basename(_root).startswith("models--"):
                            _parent = os.path.dirname(_root)
                            if _parent == _root:
                                break
                            _root = _parent
                        if os.path.basename(_root).startswith("models--"):
                            logger.warning(
                                "Embedding cache has a broken symlink (%s); clearing %s "
                                "so fastembed re-downloads real files", _onnx, _root,
                            )
                            shutil.rmtree(_root, ignore_errors=True)
            except Exception as _e:
                logger.debug("embedding cache symlink-heal skipped: %s", _e)
        kwargs = {"model_name": self.model, "cache_dir": cache_dir}
        _load_start = time.monotonic()
        self._embedding = TextEmbedding(**kwargs)
        _load_ms = (time.monotonic() - _load_start) * 1000
        self._dim: Optional[int] = None
        self.url = "local://fastembed"
        logger.info("fastembed_loaded", model=self.model, load_ms=round(_load_ms, 1))

    def get_sentence_embedding_dimension(self) -> int:
        if self._dim is not None:
            return self._dim
        vec = self.encode(["hello"])
        self._dim = vec.shape[1]
        logger.info(f"Embedding dimension: {self._dim} (model={self.model})")
        return self._dim

    def encode(
        self, texts: List[str], normalize_embeddings: bool = True,
        is_query: bool = False,
    ) -> np.ndarray:
        """Encode texts locally. Returns (N, dim) float32 array. Applies nomic's
        task prefix (query vs document) and Matryoshka truncation to _TRUNCATE_DIM."""
        if not texts:
            return np.array([], dtype="float32")

        prefixed = _prefix_texts(texts, is_query, self.model)
        vecs = np.array(list(self._embedding.embed(prefixed)), dtype="float32")
        vecs = _truncate_and_normalize(vecs, normalize_embeddings)

        if self._dim is None and vecs.size > 0:
            self._dim = vecs.shape[1]

        return vecs


class LlamaCppEmbedClient:
    """Local embedding client using llama.cpp (GGUF), the onnxruntime-free path
    for platforms fastembed can't run on (notably FreeBSD, which has no
    onnxruntime Python binding). Runs the SAME model as the fastembed default
    (nomic-embed-text-v1.5) as a GGUF, with mean pooling + L2 normalization. The
    nomic task prefixes and Matryoshka truncation are applied in encode() via the
    shared helpers, identically to the fastembed backend, so vectors stay aligned
    across the fleet. Same encode() interface as FastEmbedClient.

    Config (env): LLAMACPP_EMBED_REPO / LLAMACPP_EMBED_FILE select the GGUF (HF
    repo + filename glob)."""

    def __init__(self, model: Optional[str] = None):
        try:
            from llama_cpp import (
                Llama, LLAMA_POOLING_TYPE_MEAN, LLAMA_ROPE_SCALING_TYPE_YARN,
            )
        except ImportError as e:
            raise RuntimeError(
                "llama-cpp-python is not installed (the onnxruntime-free embedding "
                "backend). Install it (e.g. `pkg install py312-llama-cpp-python`)."
            ) from e

        self.model = model or os.getenv("FASTEMBED_MODEL", _DEFAULT_FASTEMBED_MODEL)
        repo = os.getenv("LLAMACPP_EMBED_REPO", "nomic-ai/nomic-embed-text-v1.5-GGUF")
        filename = os.getenv("LLAMACPP_EMBED_FILE", "*Q8_0.gguf")
        # Task prefix + Matryoshka truncation are applied in encode() via the
        # shared helpers, identically to the fastembed backend, so vectors stay
        # aligned across the fleet.
        os.makedirs(FASTEMBED_CACHE_DIR, exist_ok=True)

        # Two thread configs for the two workloads (measured: single-item latency
        # is flat past ~4 threads — a short encode can't feed more — while bulk
        # reindex scales with cores). n_threads drives per-item (the hot path);
        # n_threads_batch drives the rare full reindex. Defaults auto-size to the
        # box but stay overridable.
        #
        # n_threads_batch is capped at 8, not cpu_count: llama.cpp picks the
        # batch pool for any multi-TOKEN call, so every query embed uses it,
        # and an all-cores spinning OpenMP team per process collapses under
        # multi-process traffic (app + memory MCP: 2 procs on a 24-core host
        # measured 4.9 ms -> 1.3 s per embed with the uncapped pool; capped at
        # 8 the bare embed degrades to ~7-10 ms at 4 procs, a full memory
        # search to ~20-30 ms p50). Solo cost of the cap: none
        # single-item, ~15% bulk — raise LLAMACPP_EMBED_THREADS_BATCH for a
        # one-off reindex if that ever matters.
        #
        # OpenBSD is capped harder (4): its build has no OpenMP, and ggml's own
        # spin threadpool livelocks the scheduler when two processes' pools
        # exceed the CPU count — measured on a 12-vCPU guest: 2x8 threads gave
        # deterministic ~35 s stalls per embed; 2x4 runs at 13 ms. The cap
        # costs ~4 ms solo (7.5 -> 11.7 ms) and buys a working two-process
        # topology, which is not optional.
        import sys as _sys
        _cpu = os.cpu_count() or 4
        _batch_cap = 4 if _sys.platform.startswith("openbsd") else 8
        n_threads = max(1, int(os.getenv("LLAMACPP_EMBED_THREADS", str(min(4, _cpu)))))
        n_threads_batch = max(1, int(os.getenv("LLAMACPP_EMBED_THREADS_BATCH", str(min(_batch_cap, _cpu)))))
        # nomic-v1.5's GGUF trains at 2048 tokens; memory/RAG snippets are far
        # shorter, so 2048 is ample and avoids llama.cpp's n_ctx>n_ctx_train
        # overflow warning that 8192 triggers for no benefit.
        n_ctx = max(512, int(os.getenv("LLAMACPP_EMBED_CTX", "2048")))

        # nomic-v1.5's 8K context needs Dynamic-NTK RoPE, which llama.cpp lacks;
        # its documented substitute is YaRN. So whenever n_ctx exceeds the GGUF's
        # 2048 train range, engage YaRN (rope_freq_scale 0.75 per nomic's recipe)
        # instead of letting inputs run past the trained range and degrade. At the
        # default 2048 no scaling is applied (rope stays native).
        rope_kwargs = {}
        if n_ctx > 2048:
            rope_kwargs = {
                "rope_scaling_type": LLAMA_ROPE_SCALING_TYPE_YARN,
                "rope_freq_scale": float(os.getenv("LLAMACPP_EMBED_ROPE_FREQ_SCALE", "0.75")),
            }

        _load_start = time.monotonic()
        self._llm = Llama.from_pretrained(
            repo_id=repo,
            filename=filename,
            embedding=True,
            pooling_type=LLAMA_POOLING_TYPE_MEAN,
            n_ctx=n_ctx,
            n_batch=512,
            n_threads=n_threads,
            n_threads_batch=n_threads_batch,
            verbose=False,
            cache_dir=FASTEMBED_CACHE_DIR,
            **rope_kwargs,
        )
        _load_ms = (time.monotonic() - _load_start) * 1000
        self._dim: Optional[int] = None
        self.url = "local://llamacpp"
        logger.info("llamacpp_embed_loaded", model=repo, file=filename,
                    load_ms=round(_load_ms, 1))

    def get_sentence_embedding_dimension(self) -> int:
        if self._dim is not None:
            return self._dim
        self._dim = self.encode(["hello"]).shape[1]
        logger.info(f"Embedding dimension: {self._dim} (llama.cpp {self.model})")
        return self._dim

    def encode(
        self, texts: List[str], normalize_embeddings: bool = True,
        is_query: bool = False,
    ) -> np.ndarray:
        if not texts:
            return np.array([], dtype="float32")
        prefixed = _prefix_texts(texts, is_query, self.model)
        out = self._llm.embed(prefixed)
        vecs = np.array(out, dtype="float32")
        if vecs.ndim == 1:
            vecs = vecs.reshape(1, -1)
        vecs = _truncate_and_normalize(vecs, normalize_embeddings)
        if self._dim is None and vecs.size > 0:
            self._dim = vecs.shape[1]
        return vecs


def _load_persisted_endpoint() -> dict:
    """Load the custom embedding endpoint saved from the admin panel."""
    try:
        endpoint_file = EMBEDDING_ENDPOINT_FILE
        if os.path.exists(endpoint_file):
            import json
            data = json.loads(open(endpoint_file, encoding="utf-8").read())
            if data.get("url"):
                return data
    except Exception:
        pass
    return {}


def build_local_embed_client():
    """Build the local (no-HTTP) embedding client.

    llama.cpp (GGUF Q8_0) is the default on every platform: it runs the same
    nomic model everywhere including the BSDs (fastembed's onnxruntime has no BSD
    binding), per-item latency is a few ms, and unifying on one backend removes
    the fastembed/onnxruntime provisioning split. fastembed wins only bulk
    throughput, which the memory workload (one item at a time) never exercises.

    The preferred backend is tried first, the other as a fallback, so a machine
    with only one of the two installed still gets working embeddings — this keeps
    existing installs (fastembed present, llama.cpp not yet) healthy through the
    transition. EMBEDDING_LOCAL_BACKEND=fastembed flips the preference."""
    prefer_fastembed = os.getenv("EMBEDDING_LOCAL_BACKEND", "").lower() == "fastembed"
    order = ([FastEmbedClient, LlamaCppEmbedClient] if prefer_fastembed
             else [LlamaCppEmbedClient, FastEmbedClient])
    last_err = None
    for ctor in order:
        try:
            return ctor()
        except Exception as e:  # ImportError (not installed) or load failure
            last_err = e
            logger.warning("local embedding backend %s unavailable: %s",
                           ctor.__name__, e)
    raise RuntimeError(f"no local embedding backend available: {last_err}")


_http_embed_down = False  # process-level latch: skip re-probing a dead endpoint


def reset_http_embed_state():
    """Clear the 'HTTP embedding endpoint is down' latch so the next
    get_embedding_client() re-probes. Call this when the embedding endpoint
    setting changes (e.g. the user starts Ollama and saves the endpoint) —
    otherwise a latch tripped at startup would keep us on FastEmbed for the
    whole process even after the endpoint comes back."""
    global _http_embed_down
    _http_embed_down = False


def get_embedding_client():
    """Factory: try HTTP API first, fall back to the local backend
    (llama.cpp by default; fastembed when opted in)."""
    global _http_embed_down

    _factory_start = time.monotonic()

    # Check for a persisted custom endpoint (saved from admin panel)
    persisted = _load_persisted_endpoint()
    if persisted.get("url"):
        url = persisted["url"]
        model = persisted.get("model", "")
        api_key = persisted.get("api_key", "")
        # Also set in env so other code sees it
        os.environ["EMBEDDING_URL"] = url
        if model:
            os.environ["EMBEDDING_MODEL"] = model
        if api_key:
            from src.secret_storage import decrypt
            os.environ["EMBEDDING_API_KEY"] = decrypt(api_key)
    # Try the HTTP embedding API — unless we already found it down this process
    # (avoids paying the connect timeout again on every RAG/memory/tool probe).
    if not _http_embed_down:
        try:
            client = EmbeddingClient()
            client.get_sentence_embedding_dimension()  # health check
            logger.info("embedding_client_selected", backend="http",
                        url=client.url, model=client.model,
                        factory_ms=round((time.monotonic() - _factory_start) * 1000, 1))
            return client
        except Exception as e:
            _http_embed_down = True
            logger.warning(f"HTTP embedding API unavailable ({e}); using the local embedding backend for the rest of this process")

    # Fall back to the local backend (llama.cpp GGUF by default; fastembed via
    # EMBEDDING_LOCAL_BACKEND=fastembed).
    try:
        client = build_local_embed_client()
        client.get_sentence_embedding_dimension()
        logger.info("embedding_client_selected", backend=client.url,
                    model=client.model,
                    factory_ms=round((time.monotonic() - _factory_start) * 1000, 1))
        return client
    except ImportError:
        logger.error("local embedding backend not installed — run: pip install llama-cpp-python")
    except Exception as e:
        logger.error(f"Local embedding backend init failed: {e}")

    return None
