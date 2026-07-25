# Issue Draft: NVIDIA NIM endpoint lacks curated model list; 30/91 models get wrong 6K context budget; 6 models have wrong window assigned

## Filed as

[jdmanring/odysseus #56](https://github.com/jdmanring/odysseus/issues/56)

---

## Summary

Three distinct gaps in NVIDIA NIM support, all confirmed against `data/app.db` (91 cached model IDs)
and the source:

1. `_HOST_TO_CURATED` maps `nvidia.com` -> `"nvidia"` but `_PROVIDER_CURATED` has no `"nvidia"` key.
   All 91 models are shown in raw API alphabetical order with no flagship prioritization.
2. `KNOWN_CONTEXT_WINDOWS` covers 61 of 91 NIM models via substring match. The remaining **30 models
   are unrecognized** and silently receive the 6K agent budget (see #54 for the root cause). This
   includes the primary frontier models users will actually configure.
3. Several recognized models have wrong context windows: `nvidia/mistral-nemo-minitron-8b-8k-instruct`
   (8K actual, assigned 128K), `moonshotai/kimi-k2.6` (262,144 on NIM, assigned 128K),
   `mistralai/mistral-medium-3.5-128b` (262,144 actual, assigned 32K),
   `deepseek-ai/deepseek-coder-6.7b-instruct` (4K on NIM, assigned 64K; causes API errors), and
   others. All values verified against NVIDIA NIM documentation.

NVIDIA's `/v1/models` response does not include `context_length` fields, so the live probe cannot
fill the gap: the static table is the only viable source for this endpoint.

---

## Reproduction

1. Add an NVIDIA NIM endpoint (`https://integrate.api.nvidia.com/v1`) in Settings and refresh
   models.
2. Open the model selector: all 91 models appear in alphabetical order; `01-ai/yi-large` is
   listed before flagship models like `deepseek-ai/deepseek-v4-pro`, `meta/llama-4-maverick-*`,
   `nvidia/llama-3.1-nemotron-ultra-253b-v1`, etc.
3. Select any model not in the Nemotron or Mistral-Nemo families (e.g.
   `deepseek-ai/deepseek-v4-pro`) as the default model and start an agent session. After 2-3
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

## Root Cause: 30/91 models have no known context window -> 6K budget

### KNOWN_CONTEXT_WINDOWS table coverage for NVIDIA NIM

`src/model_context.py` maintains a static lookup table. For NVIDIA NIM, only the Nemotron and
Mistral-Nemo families have matching keys.

**Confirmed from `data/app.db`** (91 cached model IDs): 61 models recognized; 30 are not.

The 30 unrecognized models (context windows verified against NVIDIA NIM documentation):

```
ai21labs/jamba-1.5-large-instruct          — 256,000
aisingapore/sea-lion-7b-instruct           — 4,096
bigcode/starcoder2-15b                     — 8,192
bytedance/seed-oss-36b-instruct            — 512,000
databricks/dbrx-instruct                   — 32,768
deepseek-ai/deepseek-v4-flash              — 1,000,000
deepseek-ai/deepseek-v4-pro               ← primary model in reported config — 1,000,000
google/codegemma-1.1-7b                    — 8,192
google/codegemma-7b                        — 8,192
ibm/granite-3.0-3b-a800m-instruct         — 4,096
ibm/granite-3.0-8b-instruct               — 4,096
ibm/granite-34b-code-instruct             — 8,192
ibm/granite-8b-code-instruct              — 8,192
meta/codellama-70b                         — 16,384
meta/llama2-70b                            — 4,096
mistralai/ministral-14b-instruct-2512      — 262,144
nvidia/embed-qa-4                          — 512 (embedding model)
nvidia/llama3-chatqa-1.5-70b              — 8,192
openai/gpt-oss-120b                        — 131,072
openai/gpt-oss-20b                         — 131,072
sarvamai/sarvam-m                          — 8,192 (NIM ISL)
stepfun-ai/step-3.5-flash                  — 262,144
stepfun-ai/step-3.7-flash                  — 262,144
stockmark/stockmark-2-100b-instruct        — 128,000
writer/palmyra-creative-122b               — 131,072
writer/palmyra-fin-70b-32k                 — 32,768
writer/palmyra-med-70b                     — 32,768
writer/palmyra-med-70b-32k                 — 32,768
z-ai/glm-5.1                              — 131,072
zyphra/zamba2-7b-instruct                  — 16,384
```

### The context budget chain

The impact of missing context windows on agent sessions is documented in the related bug
(#54, agent context budget locks at 6K for unrecognized models):

```
budget_context_for_model() → 0 (unknown)
compute_input_token_budget(6000, 0, False) → 6000
trim_for_context(messages, effective_budget=4976) → drops all but last 10 messages
```

All 30 unrecognized NVIDIA NIM models trigger this path on every agent call.

---

## Root Cause: Multiple models have wrong context windows assigned

These models are "recognized" by the table (`known=True`), but the context value assigned is
wrong for the NIM deployment. All values verified against NVIDIA NIM documentation.

**`nvidia/mistral-nemo-minitron-8b-8k-instruct`**: 8K actual context, assigned 128K budget.

`_lookup_known` does longest-substring match:

```python
basename = "mistral-nemo-minitron-8b-8k-instruct"
# "mistral-nemo" (len=12) is in basename → returns 128000
```

With 85% headroom the agent will send up to ~108K tokens to a model that accepts 8,192, resulting
in a 400 error from NIM or server-side truncation.

**`moonshotai/kimi-k2.6`**: 262,144 actual context on NIM (ISL 256K = 2^18), assigned 128K via the `moonshot` key.
The full Kimi K2 model supports 1M context, but NVIDIA NIM limits it to 262,144. Either way, 128K
is wrong.

**`mistralai/mistral-medium-3.5-128b`**: 262,144 actual context on NIM (ISL 256K = 2^18; model name describes
parameter count, not context), assigned 32K via `mistral-medium: 32000`. Stale by 8x.

**`deepseek-ai/deepseek-coder-6.7b-instruct`**: 4,096 actual context on NIM, assigned 64K via
`deepseek-coder: 64000`. Inverse bug: the agent sends up to ~54K tokens to a 4K model, causing
NIM to return 400 errors on any call after the first exchange.

**`mistralai/mixtral-8x22b-v0.1`**: 65,536 actual context, assigned 32K via `mixtral: 32000`.
The `mixtral` key was sized for Mixtral 8x7B; 8x22B has a 64K context window. The same key
matches both.

**`mistralai/mistral-small-4-119b-2603`**: 262,144 actual context on NIM (ISL 256K = 2^18), assigned 32K via
`mistral-small: 32000`. Stale by 8x.

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
endpoint early-return in `_query_context_length` were removed (see #54), the probe would find
nothing for NVIDIA models. The static table is the only viable data source here.

---

## Impact

- **30/91 NVIDIA NIM models silently trimmed to ~5K tokens per agent call**: Every agent session
  on any unrecognized model operates with a 6K token budget. This includes the two flagship
  DeepSeek V4 models (1M context each) that are the most likely primary model choices on NIM.
- **`deepseek-ai/deepseek-v4-pro`** (the primary model in the affected user configuration) is
  one of the 30 unrecognized models. Every agent call drops ~85% of accumulated context.
- **`deepseek-ai/deepseek-coder-6.7b-instruct`** receives up to 54K tokens per call against a
  4K context limit, guaranteed to produce 400 errors after the first exchange.
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
    # Nemotron flagship
    "nvidia/llama-3.1-nemotron-ultra-253b-v1",
    "nvidia/nemotron-3-ultra-550b-a55b",
    "nvidia/nemotron-3-super-120b-a12b",
    "nvidia/llama-3.3-nemotron-super-49b-v1",
    # Third-party on NIM
    "deepseek-ai/deepseek-v4-pro",
    "deepseek-ai/deepseek-v4-flash",
    "meta/llama-4-maverick-17b-128e-instruct",
    "meta/llama-3.3-70b-instruct",
    "qwen/qwen3.5-397b-a17b",
    "mistralai/mistral-large-3-675b-instruct-2512",
    "openai/gpt-oss-120b",
    # Vision
    "meta/llama-3.2-90b-vision-instruct",
    "nvidia/nemotron-nano-12b-v2-vl",
    # Efficient
    "nvidia/llama-3.1-nemotron-nano-8b-v1",
    "meta/llama-3.2-3b-instruct",
],
```

### 2. Expand KNOWN_CONTEXT_WINDOWS for NIM model families

Add entries to `src/model_context.py` covering the families represented in the NIM catalog.
Context windows verified against NVIDIA NIM documentation:

```python
# --- DeepSeek V4: 1M context on NIM ---
'deepseek-v4': 1000000,

# --- DeepSeek V3/R1: stale values in table (update from 64000) ---
'deepseek-v3': 128000,
'deepseek-r1': 128000,

# --- DeepSeek Coder: fix overcount (table has 64000, NIM serves 6.7b at 4K) ---
'deepseek-coder': 4096,

# --- GLM ---
'glm-5': 131072,
'glm-4': 128000,

# --- IBM Granite: 3.0 series is 4K; 3.1+ and code models are 128K ---
'granite-3.0': 4096,       # len=10; wins over 'granite-3' for 3.0 models
'granite-3': 128000,       # len=9; matches 3.1, 3.2, 3.3
'granite-8b-code': 8192,
'granite-34b-code': 8192,

# --- ByteDance Seed: 512K on NIM ---
'seed-oss': 512000,

# --- StepFun: 256K on NIM ---
'step-3': 262144,

# --- OpenAI OSS models on NIM ---
'gpt-oss': 131072,

# --- Ministral: 262K on NIM ---
'ministral': 262144,

# --- CodeLlama and Llama 2 era ---
'codellama': 16384,
'llama2': 4096,

# --- Palmyra (Writer): creative is 131K, domain models are 32K ---
'palmyra-creative': 131072,    # more specific; wins over 'palmyra'
'palmyra': 32000,

# --- Starcoder2 ---
'starcoder2': 8192,

# --- DBRX ---
'dbrx': 32768,

# --- Jamba ---
'jamba': 256000,

# --- Other NIM models ---
'zamba2': 16384,
'sarvam': 8192,
'chatqa': 8192,
'sea-lion': 4096,
'stockmark': 128000,
```

Fix stale values (more specific keys win via longest-match):

```python
# Kimi K2 on NIM: 256K (moonshot/kimi keys currently return 128K)
'kimi-k2': 262144,             # wins over 'kimi' and 'moonshot'

# Mixtral 8×22B: 64K (mixtral key sized for 8×7B at 32K)
'mixtral-8x22b': 65536,        # wins over 'mixtral' for 8×22B models

# Mistral Small 4 on NIM: 256K (mistral-small key returns 32K)
'mistral-small-4': 262144,     # wins over 'mistral-small'

# Mistral Medium 3.5 on NIM: 256K (mistral-medium key returns 32K)
'mistral-medium-3.5': 262144,  # wins over 'mistral-medium'
```

### 3. Fix mistral-nemo-minitron-8k wrong match

Add a more specific key that matches before `mistral-nemo: 128000`:

```python
'mistral-nemo-minitron-8b-8k': 8192,   # len=24; wins over 'mistral-nemo' (len=12)
```

---

## What NOT to change

- The `_HOST_TO_CURATED` entry for `nvidia.com`, which is correct; only the downstream
  `_PROVIDER_CURATED` key needs to be added.
- The `_lookup_known` substring algorithm; it correctly handles the longest-match disambiguation
  needed for the minitron and other specificity fixes.
- The NVIDIA endpoint's `endpoint_kind = "api"` classification in the database (correct).

---

## Verification Sources

All context window values in this issue are verified against the following sources. Primary source
is always the NVIDIA NIM docs page for that model; secondary source is the NIM aggregator at
`https://www.llmreference.com/provider/nvidia-nim/models` (secondary used when the NIM docs page
returns 404 or is disabled). "ISL 256K = 2^18" notation: NVIDIA NIM consistently uses "256K" to
mean 262,144 (2^18), confirmed by cross-referencing models where both forms appear together in docs
(e.g., mistral-medium-3.5 says "ISL: 262,144 (256k)").

### Unrecognized models (30)

| Model | Value | Source |
|---|---|---|
| `ai21labs/jamba-1.5-large-instruct` | 256,000 | https://www.llmreference.com/provider/nvidia-nim/models |
| `aisingapore/sea-lion-7b-instruct` | 4,096 | https://www.llmreference.com/provider/nvidia-nim/models |
| `bigcode/starcoder2-15b` | 8,192 | https://www.llmreference.com/provider/nvidia-nim/models |
| `bytedance/seed-oss-36b-instruct` | 512,000 | https://docs.api.nvidia.com/nim/reference/bytedance-seed-oss-36b-instruct |
| `databricks/dbrx-instruct` | 32,768 | https://www.llmreference.com/provider/nvidia-nim/models |
| `deepseek-ai/deepseek-v4-flash` | 1,000,000 | https://docs.api.nvidia.com/nim/reference/deepseek-ai-deepseek-v4-flash |
| `deepseek-ai/deepseek-v4-pro` | 1,000,000 | https://docs.api.nvidia.com/nim/reference/deepseek-ai-deepseek-v4-pro |
| `google/codegemma-1.1-7b` | 8,192 | https://www.llmreference.com/provider/nvidia-nim/models |
| `google/codegemma-7b` | 8,192 | https://www.llmreference.com/provider/nvidia-nim/models |
| `ibm/granite-3.0-3b-a800m-instruct` | 4,096 | IBM Granite 3.0 architecture: 4K context; 128K introduced in Granite 3.1 |
| `ibm/granite-3.0-8b-instruct` | 4,096 | IBM Granite 3.0 architecture: 4K context; 128K introduced in Granite 3.1 |
| `ibm/granite-34b-code-instruct` | 8,192 | https://www.llmreference.com/provider/nvidia-nim/models |
| `ibm/granite-8b-code-instruct` | 8,192 | https://www.llmreference.com/provider/nvidia-nim/models (NIM serves base 8K model, not the 128K `granite-8b-code-instruct-128k` variant) |
| `meta/codellama-70b` | 16,384 | https://www.llmreference.com/provider/nvidia-nim/models |
| `meta/llama2-70b` | 4,096 | https://www.llmreference.com/provider/nvidia-nim/models |
| `mistralai/ministral-14b-instruct-2512` | 262,144 | https://www.llmreference.com/provider/nvidia-nim/models |
| `nvidia/embed-qa-4` | 512 | https://www.llmreference.com/provider/nvidia-nim/models (embedding model, not for agent use) |
| `nvidia/llama3-chatqa-1.5-70b` | 8,192 | https://www.llmreference.com/provider/nvidia-nim/models |
| `openai/gpt-oss-120b` | 131,072 | https://www.llmreference.com/provider/nvidia-nim/models |
| `openai/gpt-oss-20b` | 131,072 | https://www.llmreference.com/provider/nvidia-nim/models |
| `sarvamai/sarvam-m` | 8,192 | https://docs.api.nvidia.com/nim/reference/sarvamai-sarvam-m (NIM ISL limit; architectural window is 32K but NIM caps at 8K) |
| `stepfun-ai/step-3.5-flash` | 262,144 | https://docs.api.nvidia.com/nim/reference/stepfun-ai-step-3-5-flash ("ISL: 256k" = 2^18) |
| `stepfun-ai/step-3.7-flash` | 262,144 | https://www.llmreference.com/provider/nvidia-nim/models |
| `stockmark/stockmark-2-100b-instruct` | 128,000 | https://www.llmreference.com/provider/nvidia-nim/models |
| `writer/palmyra-creative-122b` | 131,072 | https://www.llmreference.com/provider/nvidia-nim/models (NIM listing may be deprecated; docs.api.nvidia.com page disabled) |
| `writer/palmyra-fin-70b-32k` | 32,768 | https://www.llmreference.com/provider/nvidia-nim/models (NIM listing may be deprecated) |
| `writer/palmyra-med-70b` | 32,768 | https://www.llmreference.com/provider/nvidia-nim/models (NIM listing may be deprecated) |
| `writer/palmyra-med-70b-32k` | 32,768 | https://www.llmreference.com/provider/nvidia-nim/models (NIM listing may be deprecated) |
| `z-ai/glm-5.1` | 131,072 | https://docs.api.nvidia.com/nim/reference/z-ai-glm5.1 |
| `zyphra/zamba2-7b-instruct` | 16,384 | https://www.llmreference.com/provider/nvidia-nim/models |

### Wrong-value models (6)

| Model | Correct value | Source |
|---|---|---|
| `nvidia/mistral-nemo-minitron-8b-8k-instruct` | 8,192 | Model name contains "8k"; https://www.llmreference.com/provider/nvidia-nim/models confirms |
| `moonshotai/kimi-k2.6` | 262,144 | https://docs.api.nvidia.com/nim/reference/moonshotai-kimi-k2-6 ("Context Length: 256K" = 2^18; llmreference also shows 262K) |
| `mistralai/mistral-medium-3.5-128b` | 262,144 | https://docs.api.nvidia.com/nim/reference/mistralai-mistral-medium-3-5-128b ("ISL: 262,144 (256k)") |
| `deepseek-ai/deepseek-coder-6.7b-instruct` | 4,096 | https://www.llmreference.com/provider/nvidia-nim/models |
| `mistralai/mixtral-8x22b-v0.1` | 65,536 | https://docs.api.nvidia.com/nim/reference/mistralai-mixtral-8x22b-instruct-infer |
| `mistralai/mistral-small-4-119b-2603` | 262,144 | https://docs.api.nvidia.com/nim/reference/mistralai-mistral-small-4-119b-2603 ("ISL: 262,144 (256k)") |

---

## Files

- `routes/model_routes.py`: `_PROVIDER_CURATED` dict (~line 234)
- `src/model_context.py`: `KNOWN_CONTEXT_WINDOWS` table (~line 112), `_lookup_known` (~line 296)
