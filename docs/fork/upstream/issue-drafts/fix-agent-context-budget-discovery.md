# Issue Draft: Agent context silently trimmed to ~5K tokens when model is not in KNOWN_CONTEXT_WINDOWS

## Filed as

[jdmanring/odysseus #54](https://github.com/jdmanring/odysseus/issues/54)

---

## Summary

The agent input-token budget locks at 6,000 tokens for any model not in the `KNOWN_CONTEXT_WINDOWS`
table, even when the model's actual context window is orders of magnitude larger. The budget is
supposed to auto-scale to the model's context window when it is undeclared (the default 6,000 is
the "auto" sentinel, not a real cap), but a flag mismatch in the discovery path causes auto-scaling
to silently fail for unrecognized models. The result is that every agent turn with more than ~5K
tokens of accumulated history throws away the older portion — the model effectively loses all memory
of anything that happened more than a handful of exchanges ago.

---

## Reproduction

Use any model **not** listed in `src/model_context.py :: KNOWN_CONTEXT_WINDOWS` (e.g.
`deepseek-ai/deepseek-v4-pro`, `z-ai/glm-5.1`, `bytedance/seed-oss-36b-instruct`,
`stepfun-ai/step-3.5-flash`) via an endpoint configured as `endpoint_kind = "api"` or `"proxy"`.
Leave `agent_input_token_budget` at its default (6000). After 2–3 agent exchanges the session
will have accumulated enough history to trigger trimming. The agent will thereafter behave as if
it has no memory of earlier turns.

---

## Root Cause (traced through code and confirmed in logs)

### The discovery chain

`src/agent_loop.py` computes the effective input budget before every LLM call:

```python
ctx_for_budget = budget_context_for_model(endpoint_url, model, fallback=context_length)
effective_budget = compute_input_token_budget(soft_budget, ctx_for_budget, budget_is_explicit, ...)
trimmed_messages = trim_for_context(messages, effective_budget, reserve_tokens=reserve_tokens)
```

`budget_context_for_model` (`src/model_context.py`) is the gatekeeper:

```python
def budget_context_for_model(endpoint_url, model, *, fallback=0):
    ctx, known = get_context_length_known(endpoint_url, model)
    return ctx if known else 0          # ← returns 0 when unknown
```

`compute_input_token_budget` (`src/context_budget.py`) treats 0 as "window unknown, stay
conservative":

```python
if context_length > 0:
    return max(1, min(int(context_length * headroom), hard_max))  # auto-scale
return configured if configured > 0 else default                   # fallback: 6000
```

So: unknown model → `budget_context_for_model` returns 0 → `compute_input_token_budget`
returns 6,000 → `trim_for_context` runs with effective budget of **4,976 tokens**
(6,000 − 1,024 reserve).

### Why models are "unknown"

For endpoints configured as `endpoint_kind = "api"` or `"proxy"`, `_query_context_length`
skips the network probe entirely to avoid expensive catalog downloads:

```python
if configured_kind in ("api", "proxy"):
    if known:                        # known = _lookup_known(model)
        return known, True
    return DEFAULT_CONTEXT, False    # ← known=False despite returning 128000
```

`_lookup_known` does substring matching against a static table. Any model family not in that
table returns `None`, which makes `known = False`. The function returns
`(DEFAULT_CONTEXT=128000, known=False)` — a value that looks like it was discovered but carries
a flag that prevents it from being used for auto-scaling.

### The flag survives into the budget calculation

The 128,000 context length is logged correctly:

```
"Context length for deepseek-ai/deepseek-v4-pro: 128000"
```

But `budget_context_for_model` discards it because `known=False`, returning 0. The agent
never sees the 128,000; it only sees 0 from `budget_context_for_model`, which forces the
6,000-token fallback.

### Confirmed in production logs

Every agent call in sessions using `deepseek-ai/deepseek-v4-pro` triggers:

```
Trimming messages: 82487 tokens > 4976 budget (ctx=6000)
Trimmed to 19308 tokens (11 messages)
[agent] soft-trimmed context: 82487 -> 19308 tokens (budget=6000, reserve=1024)
```

The PROTECT_RECENT floor (last 10 messages) prevents the trim from reaching the 4,976 target, but
everything older than the last 10 messages is permanently dropped — on every single call.

Aggregate across two log rotation files: **203 agent calls** triggered context trimming.
Average session size at trim time: **57,325 tokens**. Average drop per call: **49,124 tokens**
(85.6% of accumulated context discarded per call).

---

## Affected Models (incomplete — any model not in KNOWN_CONTEXT_WINDOWS)

Models confirmed to be missing from the table while being in common use (context windows
verified against NVIDIA NIM documentation):

| Model ID | Family | Actual context on NIM |
|---|---|---|
| `deepseek-ai/deepseek-v4-pro` | DeepSeek V4 | 1,000,000 |
| `deepseek-ai/deepseek-v4-flash` | DeepSeek V4 | 1,000,000 |
| `z-ai/glm-5.1` | GLM | 131,072 |
| `bytedance/seed-oss-36b-instruct` | Seed | 512,000 |
| `stepfun-ai/step-3.5-flash` | Step | 262,144 |
| `openai/gpt-oss-120b` | GPT OSS | 131,072 |
| `ibm/granite-3.0-8b-instruct` | Granite 3.0 | 4,096 |
| `meta/codellama-70b` | CodeLlama | 16,384 |

Models already in the table but with stale or wrong values:

| Key | Table value | Actual | Impact |
|---|---|---|---|
| `deepseek-v3` | 64,000 | 128,000 | 50% context underuse |
| `deepseek-coder` | 64,000 | 4,096 (NIM) | Overcount — sends 54K tokens to 4K model, causes 400 errors |
| `mixtral` | 32,000 | 65,536 (8×22B) | 50% context underuse |
| `mistral-small` | 32,000 | 262,144 (small-4 on NIM) | 8× undercount (source: docs.api.nvidia.com) |
| `mistral-medium` | 32,000 | 262,144 (medium-3.5 on NIM) | 8× undercount (source: docs.api.nvidia.com) |
| `kimi` / `moonshot` | 128,000 | 262,144 (kimi-k2.6 on NIM) | 2× undercount (source: docs.api.nvidia.com) |

Any user running a frontier model released after the table was last updated will silently receive
the 6,000-token cap. The table requires manual maintenance with no mechanism to detect when it
becomes stale.

---

## Why the 6,000 default exists (and why it cannot be the fallback)

The `DEFAULT_BUDGET = 6000` was chosen as a safe conservative default for unknown small-context
models (8K, 4K). The intent documented in `src/context_budget.py` is:

> When the window is unknown (context_length <= 0), use the conservative default budget and do
> NOT scale off the fallback.

The conservative posture is correct for a truly unknown model. The problem is that the "unknown"
classification is being applied to well-known frontier models simply because the static table
hasn't been updated. A model that the operator has explicitly configured via Settings is not
"unknown" in any meaningful sense — but the code treats it that way.

---

## Impact

- **Agent amnesia**: Every agent session using an unlisted model loses all context older than the
  most recent 10 messages, on every turn, silently. There is no warning to the user.
- **Fallback chain receives pre-trimmed context**: When a fallback model answers, it receives
  messages already trimmed to 5K tokens. Even a fallback with a 1M context window gets the
  same lobotomized history.
- **Compounds with rate-limit failures**: If the primary model is rate-limited and a fallback
  answers, the user receives a response with no memory of the session — the worst possible
  failure mode for agent work.
- **Stale `deepseek-coder` entry causes API errors**: Overcount sends up to 54K tokens to a
  model with 4K actual context; NIM returns 400 on any call after the first few exchanges.

---

## Proposed Fix

### Immediate (low risk): Expand KNOWN_CONTEXT_WINDOWS

Add missing entries to `src/model_context.py`. See #56 for the full list of additions needed for
NVIDIA NIM specifically. General additions for common frontier families:

```python
# --- DeepSeek (extended) ---
'deepseek-v4': 1000000,  # V4 series: 1M context on NIM
'deepseek-v3': 128000,   # update from 64000
'deepseek-r1': 128000,   # update from 64000
'deepseek-coder': 4096,  # update from 64000; NIM serves coder-6.7b at 4K

# --- GLM ---
'glm-5': 131072,
'glm-4': 128000,

# --- ByteDance Seed ---
'seed-oss': 512000,      # 512K on NIM

# --- StepFun ---
'step-3': 262144,        # 262,144 (ISL 256k = 2^18) on NIM (docs.api.nvidia.com confirmed)

# --- Kimi (corrected) ---
'kimi-k2': 262144,       # K2.6 on NIM: 262,144 (docs.api.nvidia.com: "Context Length: 256K" = 2^18)
```

Update stale entries:
```python
'mistral-small-4': 262144,     # was 32K via mistral-small; NIM small-4 ISL is 262,144 (docs.api.nvidia.com)
'mistral-medium-3.5': 262144,  # was 32K via mistral-medium; NIM medium-3.5 ISL is 262,144 (docs.api.nvidia.com)
'mixtral-8x22b': 65536,        # was 32K via mixtral; 8x22B has 64K context
```

### Structural (medium risk): Probe api endpoints for context fields

Remove the `api`/`proxy` early-return in `_query_context_length` and instead probe the endpoint,
trusting API-reported values when present. The original concern ("downloading the full catalog")
is addressed by the existing loop that stops at the first matching model ID. The HTTP request
cost is mitigated by the per-`(endpoint, model)` cache, which means one probe per server
lifetime per model.

```python
# Remove this block:
if configured_kind in ("api", "proxy"):
    if known:
        return known, True
    return DEFAULT_CONTEXT, False

# Allow the probe to run; then resolve:
if api_ctx and known:
    return max(api_ctx, known), True
if api_ctx:
    return api_ctx, True
if known:
    return known, True
return DEFAULT_CONTEXT, False
```

Note: many cloud APIs (including NVIDIA NIM) do not return `context_length` fields in their
`/v1/models` responses. For those, this change is a no-op — the probe runs but finds nothing,
and the known-table fallback continues to apply. The benefit accrues for APIs that do report
context fields.

### Settings exposure (independent improvement)

The `agent_input_token_budget` setting is functional but not exposed in the Settings UI. A user
who knows about this problem has no way to fix it without editing `data/settings.json` directly.
Exposing this as an explicit field (with a note that 0 or blank means "auto") would allow users
to override discovery for their specific deployment.

---

## What NOT to change

- The `known=False → budget=0 → fallback to 6000` logic for genuinely unknown small models.
  A model with 4K context that reports nothing should not get a 108K budget.
- The `PROTECT_RECENT = 10` floor in `trim_for_context`. Dropping the most recent exchange
  would be worse than dropping old history.
- The `DEFAULT_HARD_MAX = 200_000` ceiling. This correctly prevents runaway budgets on 1M+
  context models.

---

## Files

- `src/model_context.py` — `KNOWN_CONTEXT_WINDOWS` table, `_query_context_length`
- `src/context_budget.py` — `compute_input_token_budget`, `budget_is_explicit`
- `src/agent_loop.py` — budget computation call site (~line 2186)
