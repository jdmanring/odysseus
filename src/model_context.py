"""
model_context.py

Query and cache model context window sizes from OpenAI-compatible APIs.
Provides token estimation for context usage tracking.
"""

import ipaddress
import logging
import sys
from typing import Dict, List, Optional, Tuple

from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "host.docker.internal"}
_PRIVATE_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
)

# Tailscale uses the CGNAT range 100.64.0.0/10, NOT all of 100.0.0.0/8.
# A bare "100." prefix would classify public addresses (e.g. AWS ranges
# under 100.x outside the CGNAT block) as local; routes/model_routes.py
# already narrows this the same way for endpoint classification.
_TAILSCALE_CGNAT = ipaddress.ip_network("100.64.0.0/10")


def _in_tailscale_range(host: str) -> bool:
    try:
        return ipaddress.ip_address(host) in _TAILSCALE_CGNAT
    except ValueError:
        return False


def _is_private_ip_literal(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(ip in network for network in _PRIVATE_NETWORKS)


def _normalize_base_for_compare(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    for suffix in ("/chat/completions", "/models", "/completions", "/v1/messages"):
        if url.endswith(suffix):
            url = url[: -len(suffix)].rstrip("/")
    return url


def _configured_endpoint_kind(url: str) -> Optional[str]:
    """Return configured endpoint kind for a chat/base URL when available."""
    target = _normalize_base_for_compare(url)
    if not target:
        return None
    if "core.database" not in sys.modules:
        return None
    try:
        from core.database import SessionLocal, ModelEndpoint
        db = SessionLocal()
        try:
            rows = db.query(ModelEndpoint).filter(ModelEndpoint.is_enabled == True).all()
            for ep in rows:
                base = _normalize_base_for_compare(getattr(ep, "base_url", "") or "")
                if not base:
                    continue
                if target != base and not target.startswith(base + "/"):
                    continue
                kind = (getattr(ep, "endpoint_kind", None) or "auto").strip().lower()
                if kind in ("local", "api", "proxy"):
                    return kind
                if getattr(ep, "api_key", None):
                    parsed = urlparse(base)
                    host = (parsed.hostname or "").lower()
                    path = (parsed.path or "").rstrip("/")
                    if parsed.port != 11434 and "ollama" not in host and (path.endswith("/v1") or "/openai" in path):
                        return "proxy"
                return "auto"
        finally:
            db.close()
    except Exception:
        return None


def is_local_endpoint(url: str) -> bool:
    """Check if URL points to a local/private/tailscale address."""
    kind = _configured_endpoint_kind(url)
    if kind in ("api", "proxy"):
        return False
    if kind == "local":
        return True
    try:
        host = urlparse(url).hostname or ""
        return host in _LOCAL_HOSTS or _is_private_ip_literal(host) or _in_tailscale_range(host)
    except Exception:
        return False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_CONTEXT = 128000
REQUEST_TIMEOUT = 5

# Known context windows for major API models (used as fallback when /models
# endpoint doesn't report context_length).
# Substring matching — use the shortest unique prefix so variants get caught.
KNOWN_CONTEXT_WINDOWS = {
    # --- Anthropic ---
    'claude-sonnet-4-5': 200000,
    'claude-sonnet-4-6': 200000,
    'claude-sonnet-4': 200000,
    'claude-opus-4': 200000,
    'claude-haiku-4': 200000,
    'claude-haiku-3-5': 200000,
    'claude-3-5-sonnet': 200000,
    'claude-3-5-haiku': 200000,
    'claude-3-opus': 200000,
    'claude-3-sonnet': 200000,
    'claude-3-haiku': 200000,

    # --- OpenAI ---
    'gpt-5': 400000,
    'gpt-4.1': 1047576,
    'gpt-4.1-mini': 1047576,
    'gpt-4.1-nano': 1047576,
    'gpt-4o': 128000,
    'gpt-4o-mini': 128000,
    'gpt-4-turbo': 128000,
    'gpt-4': 8192,
    'gpt-3.5-turbo': 16385,
    'o1': 200000,
    'o1-mini': 128000,
    'o1-pro': 200000,
    'o3': 200000,
    'o3-mini': 200000,
    'o4-mini': 200000,

    # --- DeepSeek ---
    'deepseek-chat': 64000,
    'deepseek-coder': 64000,
    'deepseek-reasoner': 64000,
    'deepseek-r1': 64000,
    'deepseek-v3': 64000,
    'deepseek-v2': 64000,

    # --- Google ---
    'gemini-2.5-pro': 1048576,
    'gemini-2.5-flash': 1048576,
    'gemini-2.0-flash': 1048576,
    'gemini-1.5-pro': 1048576,
    'gemini-1.5-flash': 1048576,
    'gemma-4': 262144,
    'gemma-3': 128000,
    'gemma-2': 8192,
    'codegemma': 8192,  # Google CodeGemma (NIM catalog); not matched by gemma-N keys

    # --- Mistral ---
    'mistral-large': 128000,
    'mistral-medium': 32000,
    'mistral-small': 32000,
    'mistral-nemo': 128000,
    'mistral-7b': 32000,
    'mixtral': 32000,
    'codestral': 32000,
    'pixtral': 128000,

    # --- xAI ---
    'grok-4': 131072,
    'grok-3': 131072,
    'grok-2': 131072,

    # --- Meta / Llama ---
    'llama-4': 1048576,
    'llama-3.3': 131072,
    'llama-3.2': 131072,
    'llama-3.1': 131072,
    'llama-3': 131072,

    # --- Qwen ---
    'qwen3': 131072,
    'qwen2.5': 131072,
    'qwen2': 32768,
    'qwq': 32768,

    # --- Cohere ---
    'command-r-plus': 128000,
    'command-r': 128000,
    'command-a': 256000,

    # --- Perplexity ---
    'sonar-pro': 200000,
    'sonar': 128000,

    # --- MiniMax ---
    'minimax': 1000000,

    # --- Moonshot / Kimi ---
    'moonshot': 128000,
    'kimi-k2': 262144,   # K2.x on NIM: ISL 256K = 2^18; longer key beats 'kimi'/'moonshot'
    'kimi': 128000,

    # --- Microsoft ---
    'phi-4': 16000,
    'phi-3': 128000,

    # --- Nvidia ---
    'nemotron': 131072,
    # mistral-nemo-minitron-8b-8k-instruct has an 8K ISL despite sharing the
    # 'mistral-nemo' prefix (which maps to 128K). The longer key wins via
    # _lookup_known's longest-substring rule.
    'mistral-nemo-minitron-8b-8k': 8192,

    # --- DeepSeek (extended) ---
    # V4 adds 1M context; V3/R1 shipped at 128K (table had stale 64K from V2
    # era). Coder key corrected: NIM serves deepseek-coder-6.7b at 4K, and the
    # old 64K value caused the agent to over-send and receive 400 errors.
    'deepseek-v4': 1000000,
    'deepseek-v3': 128000,   # update: was 64000
    'deepseek-r1': 128000,   # update: was 64000
    'deepseek-coder': 4096,  # update: NIM serves 6.7b at 4K; was 64000

    # --- GLM (Z.ai / ZhipuAI) ---
    'glm-5': 131072,
    'glm-4': 128000,

    # --- ByteDance Seed ---
    'seed-oss': 512000,

    # --- StepFun ---
    # NIM ISL is 262,144 ("256K" in NIM docs = 2^18, confirmed via cross-reference
    # with models where the page shows "ISL: 262,144 (256k)" explicitly).
    'step-3': 262144,

    # --- Mistral (stale-value overrides) ---
    # More specific keys beat the shorter 'mistral-small'/'mistral-medium' entries.
    'mistral-small-4': 262144,    # NIM ISL 262,144; was 32K via 'mistral-small'
    'mistral-medium-3.5': 262144, # NIM ISL 262,144; was 32K via 'mistral-medium'
    'mixtral-8x22b': 65536,       # 8x22B has 64K; was 32K via 'mixtral' (sized for 8x7B)

    # --- NVIDIA NIM catalog additions ---
    # Models present in the NIM endpoint catalog that have no existing key.
    # Context windows from docs.api.nvidia.com; secondary source llmreference.com
    # where the primary page is disabled or returns 404.
    'ministral': 262144,          # ministral-14b-instruct-2512 (NIM ISL 256K = 2^18)
    'codellama': 16384,
    'llama2': 4096,
    'palmyra-creative': 131072,   # longer key beats 'palmyra' for creative-122b
    'palmyra': 32768,             # fin/med domain models
    'starcoder2': 8192,
    'dbrx': 32768,
    'jamba': 256000,
    'zamba2': 16384,
    # sarvam-m: NIM ISL is 8,192 (NIM caps input at 8K even though the model
    # architecture supports 32K). Value from docs.api.nvidia.com/nim/reference/sarvamai-sarvam-m.
    'sarvam': 8192,
    'chatqa': 8192,
    'sea-lion': 4096,
    'stockmark': 128000,
    'gpt-oss': 131072,            # OpenAI OSS models hosted on NIM
    # granite-3.0 series (4K) vs granite-3.1+ (128K): the more specific key wins.
    'granite-3.0': 4096,
    'granite-3': 128000,
    'granite-8b-code': 8192,      # NIM serves base 8K model, not the 128K variant
    'granite-34b-code': 8192,
    # embed-qa-4 is an embedding model; agents should not be pointed at it, but
    # its context cap is 512 so over-sending would immediately fail.
    'embed-qa': 512,

    # --- Yi ---
    'yi-large': 32768,
    'yi-1.5': 16384,

    # --- 01.ai ---
    'yi-lightning': 16384,

    # --- Nous ---
    'hermes': 131072,
    'nous-hermes': 131072,

    # --- LongCat (Meituan) ---
    'longcat': 1048576,  # LongCat-2.0-Preview: 1M token context window

    # --- Open community ---
    'dolphin': 32768,
    'mythomax': 4096,
    'wizard': 32768,
    'openchat': 8192,
    'solar': 32768,
}

# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
_context_cache: Dict[Tuple[str, str], Tuple[int, bool]] = {}


def _get_context_length_cached(endpoint_url: str, model: str) -> Tuple[int, bool]:
    """Return (context_length, known). ``known`` is False only when the value is a
    bare DEFAULT_CONTEXT fallback (no endpoint report and not in the known table)."""
    configured_kind = _configured_endpoint_kind(endpoint_url)
    is_local = is_local_endpoint(endpoint_url)
    # Key on (endpoint_url, model): the same model id can be served by two
    # different remote endpoints with different real context windows (e.g. a
    # capped proxy vs. the full provider), so caching by model id alone would
    # serve one endpoint's window for the other (issue #2603).
    cache_key = (endpoint_url, model)
    if not is_local and cache_key in _context_cache:
        return _context_cache[cache_key]

    ctx, known = _query_context_length(endpoint_url, model)
    # Only cache non-default values to allow retry on next request.
    # Local endpoints can restart with a different --max-model-len while keeping
    # the same model id, so always re-query them instead of serving stale cache.
    if not is_local and (ctx != DEFAULT_CONTEXT or configured_kind in ("api", "proxy")):
        _context_cache[cache_key] = (ctx, known)
    logger.info(f"Context length for {model}: {ctx}")
    return ctx, known


def get_context_length(endpoint_url: str, model: str) -> int:
    """Get the context window size for a model.

    Queries /v1/models on the endpoint and looks for context_length
    or context_window fields. Caches result per (endpoint, model).
    Falls back to DEFAULT_CONTEXT if unavailable.
    """
    return _get_context_length_cached(endpoint_url, model)[0]


def get_context_length_known(endpoint_url: str, model: str) -> Tuple[int, bool]:
    """Like ``get_context_length`` but also returns whether the window was actually
    discovered (endpoint-reported or in the known-models table) rather than the bare
    DEFAULT_CONTEXT fallback. Callers that *scale* a budget off the window must not
    trust an unknown value — a fallback 128K isn't proof the model holds 128K
    (review on #4122)."""
    return _get_context_length_cached(endpoint_url, model)


def budget_context_for_model(endpoint_url: str, model: str, *, fallback: int = 0) -> int:
    """Context window to scale the agent input budget against.

    Returns the *freshly discovered* window when it was actually proven
    (endpoint-reported / known table), else 0 so auto-scaling stays conservative.
    Crucially this binds the ``known`` flag to the value it proves — callers must
    not pair this flag with a context length from a *different* lookup (a stale
    local re-query, or a caller that didn't pass one), which would budget off an
    unproven number (review on #4122). On probe error, returns ``fallback`` (the
    caller's best-known value) to preserve prior behaviour."""
    try:
        ctx, known = get_context_length_known(endpoint_url, model)
        return ctx if known else 0
    except Exception:
        return fallback


def _lookup_known(model: str) -> Optional[int]:
    """Check known context windows by substring match.

    Scoring: basename matches score len(key)*2; full-name-only matches score
    len(key). The double weight prevents org-prefix false positives — e.g.
    'moonshot' (len 8) would otherwise beat 'kimi-k2' (len 7) by matching
    'moonshotai' in the org portion of 'moonshotai/kimi-k2.6', even though
    'kimi-k2' is the more specific and correct key.
    """
    name = model.lower()
    basename = name.split("/")[-1] if "/" in name else name
    basename = basename.split(":")[0]  # strip :free, :extended etc.
    best_key: Optional[str] = None
    best_ctx: Optional[int] = None
    best_score: int = -1
    for key, ctx in KNOWN_CONTEXT_WINDOWS.items():
        in_basename = key in basename
        if not in_basename and key not in name:
            continue
        score = len(key) * 2 if in_basename else len(key)
        if score > best_score:
            best_key, best_ctx, best_score = key, ctx, score
    return best_ctx


def _query_context_length(endpoint_url: str, model: str) -> Tuple[int, bool]:
    """Query the model API for context length. Returns (context_length, known) where
    ``known`` is False only for the bare DEFAULT_CONTEXT fallback."""
    known = _lookup_known(model)
    api_ctx = None
    configured_kind = _configured_endpoint_kind(endpoint_url)

    # Large OpenAI-compatible proxies can make /models expensive. If the
    # endpoint is explicitly configured as API/proxy, prefer known context
    # metadata (or the default) over downloading the full catalog.
    if configured_kind in ("api", "proxy"):
        if known:
            logger.info(f"Using known context window for {model}: {known}")
            return known, True
        return DEFAULT_CONTEXT, False

    # Try llama.cpp /slots endpoint first — reports actual serving context
    if is_local_endpoint(endpoint_url):
        try:
            base = endpoint_url.split("/v1")[0] if "/v1" in endpoint_url else endpoint_url.rsplit("/", 1)[0]
            r = httpx.get(f"{base}/slots", timeout=REQUEST_TIMEOUT)
            if r.is_success:
                slots = r.json()
                if isinstance(slots, list) and slots:
                    n_ctx = slots[0].get("n_ctx")
                    if n_ctx and isinstance(n_ctx, int) and n_ctx > 0:
                        logger.info(f"llama.cpp /slots reports n_ctx={n_ctx} for {model}")
                        return n_ctx, True
        except Exception:
            pass

    # GitHub Copilot's /models requires auth + X-GitHub-Api-Version headers that
    # aren't available here; an unauthenticated probe just 400s. All Copilot
    # picker models are major API models covered by the known-context table, so
    # rely on that instead of a doomed network call.
    from src.copilot import is_copilot_base
    if is_copilot_base(endpoint_url):
        if known:
            logger.info(f"Using known context window for {model}: {known}")
            return known, True
        return DEFAULT_CONTEXT, False

    from src.endpoint_resolver import build_models_url

    models_url = build_models_url(endpoint_url)
    try:
        r = httpx.get(models_url, timeout=REQUEST_TIMEOUT)
        if r.is_success:
            data = r.json()
            models_list = data.get("data") or []

            for m in models_list:
                mid = m.get("id", "")
                if mid == model or mid.split("/")[-1] == model.split("/")[-1]:
                    for field in (
                        "context_length",
                        "context_window",
                        "max_model_len",
                        "max_context_length",
                        "max_seq_len",
                    ):
                        val = m.get(field)
                        if val and isinstance(val, (int, float)) and val > 0:
                            api_ctx = int(val)
                            break

                    if not api_ctx:
                        meta = m.get("meta") or m.get("model_extra") or {}
                        if isinstance(meta, dict):
                            # n_ctx is the actual serving context (set via -c flag in llama.cpp)
                            for field in ("n_ctx", "context_length", "context_window", "max_model_len"):
                                val = meta.get(field)
                                if val and isinstance(val, (int, float)) and val > 0:
                                    api_ctx = int(val)
                                    break
                    break
    except Exception as e:
        logger.debug(f"Failed to query context length for {model}: {e}")

    # For local/self-hosted endpoints, trust the API value (user set --max-model-len)
    # For cloud APIs, use the larger value (API can report low defaults)
    if api_ctx and known:
        _is_local = is_local_endpoint(endpoint_url)
        if _is_local and api_ctx < known:
            logger.info(f"Local endpoint reports {api_ctx} for {model} (known max: {known}) — using API value")
            return api_ctx, True
        result = max(api_ctx, known)
        if api_ctx < known:
            logger.info(f"API reported {api_ctx} for {model}, using known {known} instead")
        return result, True
    if api_ctx:
        return api_ctx, True
    if known:
        logger.info(f"Using known context window for {model}: {known}")
        return known, True

    return DEFAULT_CONTEXT, False


def estimate_tokens(messages: List[Dict]) -> int:
    """Rough token estimate for a list of messages.

    Uses chars * 0.3 which is closer to real BPE tokenizer output
    than the commonly-cited chars/4 (which underestimates by ~20-30%).
    Also adds ~4 tokens per message for role/formatting overhead, and counts
    assistant tool_calls (name + arguments) — a tool-only turn carries
    content=None with the real payload in tool_calls, so ignoring them made the
    estimate (and the compaction/trim gates that rely on it) blind to large
    tool arguments.
    """
    total = 0
    for msg in messages:
        total += 4  # per-message overhead (role, separators)
        content = msg.get("content", "")
        if isinstance(content, str):
            total += int(len(content) * 0.3)
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    total += int(len(item.get("text", "")) * 0.3)
        # Tool calls carry real payload too: a tool-only assistant turn is stored
        # with content=None and the actual args (e.g. a create_document body) in
        # tool_calls[].function.arguments. Ignoring them made large tool arguments
        # read as ~0 tokens, so the compaction/trim gates missed genuine overflow.
        tool_calls = msg.get("tool_calls")
        if isinstance(tool_calls, list):
            for tc in tool_calls:
                if not isinstance(tc, dict):
                    continue
                fn = tc.get("function") if isinstance(tc.get("function"), dict) else tc
                name = fn.get("name", "") or ""
                args = fn.get("arguments", "") or ""
                if not isinstance(args, str):
                    args = str(args)  # some shapes store arguments as a dict
                total += 4  # per tool-call overhead (id, type, wrapper)
                total += int((len(str(name)) + len(args)) * 0.3)
    return total
