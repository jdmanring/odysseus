# Issue Draft: NVIDIA NIM endpoint lacks curated model list and has wrong/missing context windows for 69 of 91 models

## Summary

Odysseus recognizes the `integrate.api.nvidia.com` endpoint as NVIDIA (`_HOST_TO_CURATED` maps
`"nvidia.com"` → `"nvidia"`), but there is no `"nvidia"` entry in `_PROVIDER_CURATED`. As a
result, all 91 NVIDIA NIM catalog models are shown to the user in raw API alphabetical order with
no flagship prioritization. Additionally, `KNOWN_CONTEXT_WINDOWS` has entries for only the
Nemotron and Mistral-Nemo model families — 69 of 91 NIM models have no known context window and
silently fall back to the 6,000-token agent budget. One model has the wrong context window
assigned. NVIDIA's `/v1/models` API does not include `context_length` fields, so the live probe
cannot fill this gap.

---

## Reproduction

1. Add an NVIDIA NIM endpoint (`https://integrate.api.nvidia.com/v1`) in Settings and refresh
   models.
2. Open the model selector: all 91 models appear in alphabetical order — `01-ai/yi-large` is
   listed before flagship models like `deepseek-ai/deepseek-v4-pro`, `meta/llama-4-maverick-*`,
   `nvidia/llama-3.1-nemotron-ultra-253b-v1`, etc.
3. Select any model not in the Nemotron or Mistral-Nemo families (e.g.
   `deepseek-ai/deepseek-v4-pro`) as the default model and start an agent session. After 2–3
   exchanges, the agent loses context.

---

## Root Cause: No curated model list for NVIDIA

### _PROVIDER_CURATED has no "nvidia" key

`routes/model_routes.py`, `_PROVIDER_CURATED`:

```python
_PROVIDER_CURATED = {
    "openai": [...],
    "anthropic": [...],
    "zai": [...],
    "deepseek": [...],
    "groq": [...],
    "mistral": [...],
    "together": [...],
    "fireworks": [...],
    "google": [...],
    "xai": [...],
    # No "nvidia" entry
}
```

`_HOST_TO_CURATED` correctly maps `nvidia.com` to the `"nvidia"` key:

```python
_HOST_TO_CURATED = (
    ...
    ("nvidia.com", "nvidia"),    # recognized, but no curated list exists
    ...
)
```

`_curate_models` falls through when no curated list exists:

```python
def _curate_models(model_ids, provider):
    curated_list = _PROVIDER_CURATED.get(provider)
    if not curated_list:
        return model_ids, []    # all 91 models treated as curated; no ordering
```

All 91 models are returned in the `curated` bucket in raw API alphabetical order.

---

## Root Cause: 69/91 models have no known context window → 6K budget

### KNOWN_CONTEXT_WINDOWS table coverage for NVIDIA NIM

`src/model_context.py` maintains a static lookup table. For NVIDIA NIM, only two families match:

| Key | Context | Models matched |
|-----|---------|---------------|
| `nemotron` | 131,072 | 20 models (Nemotron family) |
| `mistral-nemo` | 128,000 | 2 models (plus 1 incorrectly matched — see below) |

**Confirmed from `data/app.db`** (91 cached model IDs): 22 models have a known context window;
69 do not.

The 69 models with no known context include the most-used models on the endpoint:

| Model | Actual context | Gets budget |
|---|---|---|
| `deepseek-ai/deepseek-v4-pro` | 128,000 | 6,000 |
| `deepseek-ai/deepseek-v4-flash` | 128,000 | 6,000 |
| `deepseek-ai/deepseek-coder-6.7b-instruct` | 16,000 | 6,000 |
| `meta/llama-3.3-70b-instruct` | 128,000 | 6,000 |
| `meta/llama-4-maverick-17b-128e-instruct` | 1,048,576 | 6,000 |
| `qwen/qwen3.5-122b-a10b` | 131,072 | 6,000 |
| `qwen/qwen3.5-397b-a17b` | 131,072 | 6,000 |
| `stepfun-ai/step-3.5-flash` | 131,072 | 6,000 |
| `stepfun-ai/step-3.7-flash` | 262,144 | 6,000 |
| `z-ai/glm-5.1` | 128,000 | 6,000 |
| `openai/gpt-oss-120b` | 128,000 | 6,000 |
| `openai/gpt-oss-20b` | 64,000 | 6,000 |
| `mistralai/mistral-large-3-675b-instruct-2512` | 128,000 | 6,000 |
| `mistralai/mistral-medium-3.5-128b` | 128,000 | 6,000 |
| `google/gemma-4-31b-it` | 131,072 | 6,000 |
| `minimaxai/minimax-m3` | 1,000,192 | 6,000 |
| `moonshotai/kimi-k2.6`* | 1,048,576 | 128,000 (wrong key) |

*`kimi-k2.6` matches the `kimi` key → 128,000, but Kimi K2 has a 1M context window.

Full list of 69 unrecognized models: all models in `data/app.db` not matching `nemotron` or
`mistral-nemo` substrings.

### The context budget chain

The impact of missing context windows on agent sessions is documented in the related bug
(Issue A — agent context budget locks at 6K for unrecognized models):

```
budget_context_for_model() → 0 (unknown)
compute_input_token_budget(6000, 0, False) → 6000
trim_for_context(messages, effective_budget=4976) → drops all but last 10 messages
```

69 of 91 NVIDIA NIM models trigger this path on every agent call.

---

## Root Cause: One model has provably wrong context window

`nvidia/mistral-nemo-minitron-8b-8k-instruct` contains `8k` in its name — it is an 8,192-token
context model. The `_lookup_known` substring match hits `mistral-nemo: 128000` because
`mistral-nemo` appears in `mistral-nemo-minitron-8b-8k-instruct`:

```python
basename = "mistral-nemo-minitron-8b-8k-instruct"
key = "mistral-nemo"
key in basename  # → True → context 128,000 assigned
```

This model receives a 128K agent budget when its actual context is 8K. The agent will send up
to 108,800 tokens to a model that can only accept 8,192, resulting in a 400 error or silent
truncation on the server side.

---

## Root Cause: NVIDIA NIM /v1/models does not return context_length

The live API probe in `_query_context_length` would normally catch unknown models if the provider
returns `context_length` in its `/v1/models` response. NVIDIA NIM does not:

```json
{
  "object": "list",
  "data": [
    {
      "id": "deepseek-ai/deepseek-v4-pro",
      "object": "model",
      "created": ...,
      "owned_by": "deepseek-ai"
    }
  ]
}
```

No `context_length`, `context_window`, or equivalent field is present. Even if the `api`
endpoint early-return in `_query_context_length` were removed (see related Issue A), the probe
would find nothing for NVIDIA models. The static table is the only viable data source here.

---

## Impact

- **69/91 NVIDIA NIM models silently trimmed to ~5K tokens per agent call**: Every agent session
  on any non-Nemotron, non-Mistral-Nemo NVIDIA model operates with a 6K token budget. This
  includes the flagship models users are most likely to select.
- **`deepseek-ai/deepseek-v4-pro`** — the primary model in the affected user configuration —
  is one of the 69 unrecognized models. Every agent call drops ~85% of accumulated context.
- **`nvidia/mistral-nemo-minitron-8b-8k-instruct`** will receive up to 108K tokens on every
  call, likely resulting in server-side rejection.
- **No model curation**: Users adding an NVIDIA NIM endpoint see `01-ai/yi-large` and
  `abacusai/dracarys-llama-3.1-70b-instruct` before any current-generation flagship, making
  initial model selection confusing.

---

## Proposed Fix

### 1. Add a curated model list for NVIDIA NIM

Add an `"nvidia"` entry to `_PROVIDER_CURATED` in `routes/model_routes.py`, featuring current
flagship models in priority order:

```python
"nvidia": [
    # Flagship reasoning / chat
    "nvidia/llama-3.1-nemotron-ultra-253b-v1",
    "nvidia/nemotron-3-ultra-550b-a55b",
    "nvidia/nemotron-3-super-120b-a12b",
    "nvidia/llama-3.3-nemotron-super-49b-v1",
    "deepseek-ai/deepseek-v4-pro",
    "deepseek-ai/deepseek-v4-flash",
    "meta/llama-4-maverick-17b-128e-instruct",
    "meta/llama-3.3-70b-instruct",
    "qwen/qwen3.5-397b-a17b",
    "qwen/qwen3.5-122b-a10b",
    "mistralai/mistral-large-3-675b-instruct-2512",
    "openai/gpt-oss-120b",
    # Vision
    "meta/llama-3.2-90b-vision-instruct",
    "nvidia/nemotron-nano-12b-v2-vl",
    # Efficient / small
    "nvidia/llama-3.1-nemotron-nano-8b-v1",
    "meta/llama-3.2-3b-instruct",
],
```

### 2. Expand KNOWN_CONTEXT_WINDOWS for common NIM model families

Add entries to `src/model_context.py` covering the families represented in the NIM catalog:

```python
# --- Meta Llama ---
'llama-4': 1048576,       # Llama 4 series: 1M context
'llama-3.3': 128000,
'llama-3.2': 128000,
'llama-3.1': 128000,
'llama-2': 4096,
'llama2': 4096,
'codellama': 16000,

# --- DeepSeek (extended) ---
'deepseek-v4': 128000,
'deepseek-coder': 16000,

# --- Mistral (extended) ---
'mistral-large': 131072,
'mistral-medium': 131072,
'mistral-small': 32000,
'mistral-7b': 32000,
'ministral': 131072,
'mixtral': 65536,
'codestral': 32000,

# --- Qwen ---
'qwen3.5': 131072,
'qwen3': 131072,
'qwen2.5': 131072,

# --- Google Gemma ---
'gemma-4': 131072,
'gemma-3': 131072,
'gemma-2': 8192,
'gemma-2b': 8192,

# --- IBM Granite ---
'granite-3': 128000,
'granite-8b-code': 128000,
'granite-34b-code': 8192,

# --- Microsoft Phi ---
'phi-4': 16384,
'phi-3.5': 128000,
'phi-3-vision': 128000,

# --- StepFun ---
'step-3': 131072,
'step-3.7': 262144,

# --- GLM ---
'glm-5': 128000,
'glm-4': 128000,

# --- MiniMax ---
'minimax-m3': 1000192,
'minimax-m2': 128000,

# --- Kimi (corrected) ---
'kimi-k2': 1048576,        # K2 series: 1M context

# --- Others ---
'gpt-oss': 128000,         # OpenAI OSS models on NIM
'palmyra': 32000,
'solar': 4096,
'dbrx': 32768,
'jamba': 256000,
'starcoder2': 16384,
```

### 3. Fix mistral-nemo-minitron-8k context window

Add a more specific key that matches before the generic `mistral-nemo: 128000`:

```python
'mistral-nemo-minitron-8b-8k': 8192,   # before 'mistral-nemo' in table; longest-match wins
```

`_lookup_known` uses longest-substring match, so the longer key will win when present.

---

## What NOT to change

- The `_HOST_TO_CURATED` entry for `nvidia.com` — it is correct; only the downstream
  `_PROVIDER_CURATED` key needs to be added.
- The `_lookup_known` substring algorithm — it correctly handles the longest-match disambiguation
  needed for the minitron fix.
- The NVIDIA endpoint's `endpoint_kind = "api"` classification in the database — correct.

---

## Files

- `routes/model_routes.py` — `_PROVIDER_CURATED` dict (~line 234)
- `src/model_context.py` — `KNOWN_CONTEXT_WINDOWS` table (~line 112), `_lookup_known` (~line 296)
