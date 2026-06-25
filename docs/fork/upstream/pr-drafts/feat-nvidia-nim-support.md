# PR Draft: feat/nvidia-nim-support → pewdiepie-archdaemon/odysseus:dev

**Branch:** `feat/nvidia-nim-support`
**Issue:** [#56](https://github.com/jdmanring/odysseus/issues/56) (fork tracking)
**Status:** Ready to file

---

## Title

`feat(model-context): expand context window table for NVIDIA NIM catalog`

---

## Summary

### Problem

Odysseus ships a static `KNOWN_CONTEXT_WINDOWS` table keyed by substring match. Any
model whose name contains no matching key falls back to `(DEFAULT_CONTEXT=128000,
known=False)`. When `known=False`, `budget_context_for_model` returns `0`, which
disables auto-scaling and locks `agent_input_token_budget` at its 6000-token sentinel
value — trimming 85% of agent context on every call.

Separately, NVIDIA NIM models appear in raw alphabetical order in the model picker
because `_PROVIDER_CURATED` has no `"nvidia"` entry.

### What changed

**`src/model_context.py` — `KNOWN_CONTEXT_WINDOWS`:**

30 NIM model families previously unrecognized:

| Family | Key | NIM ISL |
|--------|-----|---------|
| DeepSeek V4 Pro/Flash | `deepseek-v4` | 1,000,000 |
| GLM-5 | `glm-5` | 131,072 |
| Seed-OSS 36B | `seed-oss` | 512,000 |
| Step-3 (3.5/3.7 flash) | `step-3` | 262,144 |
| GPT-OSS 120B/20B | `gpt-oss` | 131,072 |
| Granite 3.0 8B/3B | `granite-3.0` | 4,096 |
| Granite 3.x (3.1+) | `granite-3` | 128,000 |
| Granite 34B Code | `granite-34b-code` | 8,192 |
| Granite 8B Code | `granite-8b-code` | 8,192 |
| CodeLlama 70B | `codellama` | 16,384 |
| Llama 2 | `llama2` | 4,096 |
| Ministral 14B | `ministral` | 262,144 |
| Sarvam-M | `sarvam` | 8,192 |
| StarCoder2 15B | `starcoder2` | 8,192 |
| DBRX Instruct | `dbrx` | 32,768 |
| Jamba 1.5 Large | `jamba` | 256,000 |
| Zamba2 7B | `zamba2` | 16,384 |
| ChatQA 1.5 | `chatqa` | 8,192 |
| SEA-LION 7B | `sea-lion` | 4,096 |
| Stockmark 100B | `stockmark` | 128,000 |
| Palmyra Creative 122B | `palmyra-creative` | 131,072 |
| Palmyra (Fin/Med) | `palmyra` | 32,768 |
| Embed-QA-4 | `embed-qa` | 512 |
| CodeGemma 1.1/7B | `codegemma` | 8,192 |
| Mistral Small 4 | `mistral-small-4` | 262,144 |
| Mistral Medium 3.5 | `mistral-medium-3.5` | 262,144 |
| Mixtral 8×22B | `mixtral-8x22b` | 65,536 |
| Kimi K2 | `kimi-k2` | 262,144 |
| Minitron-8k | `mistral-nemo-minitron-8b-8k` | 8,192 |

6 stale value corrections (recognized models with wrong windows):

| Key | Old value | Corrected | Notes |
|-----|-----------|-----------|-------|
| `deepseek-r1` | 64,000 | 128,000 | Production context |
| `deepseek-v3` | 64,000 | 128,000 | Production context |
| `deepseek-coder` | 64,000 | 4,096 | NIM serves deepseek-coder-6.7b; overcount causes 400 errors |
| `mixtral` | 32,000 | 65,536 | Key now matches 8×7B only; 8×22B has its own key |
| `mistral-small` | 32,000 | 262,144 | mistral-small-4-119b-2603 on NIM |
| `mistral-medium` | 32,000 | 262,144 | mistral-medium-3.5-128b on NIM |

**`src/model_context.py` — `_lookup_known` scoring fix:**

Basename matches now score `len(key) * 2`; full-name-only matches score `len(key)`.
Without this, `'moonshot'` (len 8) beat `'kimi-k2'` (len 7) by matching `'moonshotai'`
in the org prefix of `'moonshotai/kimi-k2.6'`, returning 128K instead of the correct
262K ISL value.

**`routes/model_routes.py` — `_PROVIDER_CURATED`:**

Added `"nvidia"` entry with 15 ranked models so the NIM catalog is presented with
flagship models first rather than raw alphabetically. All model IDs verified against
NVIDIA NIM documentation before filing.

**`routes/model_routes.py` — endpoint auto-name fallback:**

When an endpoint is added without an explicit name (e.g. by typing the URL directly
rather than using the provider picker), the backend previously extracted the raw
hostname — `integrate.api.nvidia.com` for NIM — which then appeared verbatim in
Added Models and AI Defaults. The fallback now calls `_provider_label()` first; for
recognised providers it uses the friendly name ("NVIDIA", "OpenAI", "Anthropic", etc.).
Local and unrecognised endpoints continue using the hostname, where it remains more
informative.

Curated list with documentation citations:

| Model ID | Docs |
|----------|------|
| `nvidia/llama-3.1-nemotron-ultra-253b-v1` | [docs.api.nvidia.com](https://docs.api.nvidia.com/nim/reference/nvidia-llama-3_1-nemotron-ultra-253b-v1) |
| `nvidia/nemotron-3-ultra` | [docs.api.nvidia.com](https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3-ultra-550b-a55b) |
| `nvidia/nemotron-3-super` | [docs.api.nvidia.com](https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3-super-120b-a12b) |
| `nvidia/llama-3.3-nemotron-super-49b-v1.5` | [docs.api.nvidia.com](https://docs.api.nvidia.com/nim/reference/nvidia-llama-3_3-nemotron-super-49b-v1_5) |
| `deepseek-ai/deepseek-v4-pro` | [docs.api.nvidia.com](https://docs.api.nvidia.com/nim/reference/deepseek-ai-deepseek-v4-pro) |
| `deepseek-ai/deepseek-v4-flash` | [docs.api.nvidia.com](https://docs.api.nvidia.com/nim/reference/deepseek-ai-deepseek-v4-flash) |
| `meta/llama-4-maverick-17b-128e-instruct` | [docs.api.nvidia.com](https://docs.api.nvidia.com/nim/reference/meta-llama-4-maverick-17b-128e-instruct) |
| `meta/llama-3.3-70b-instruct` | [docs.api.nvidia.com](https://docs.api.nvidia.com/nim/reference/meta-llama-3_3-70b-instruct) |
| `qwen/qwen3.5-397b-a17b` | [docs.api.nvidia.com](https://docs.api.nvidia.com/nim/reference/qwen-qwen3-5-397b-a17b) |
| `mistralai/Mistral-Large-3-675B-Instruct-2512` | [docs.api.nvidia.com](https://docs.api.nvidia.com/nim/reference/mistralai-mistral-large-3-675b-instruct-2512) |
| `openai/gpt-oss-120b` | [docs.api.nvidia.com](https://docs.api.nvidia.com/nim/reference/openai-gpt-oss-120b) |
| `meta/llama-3.2-90b-vision-instruct` | [docs.api.nvidia.com](https://docs.api.nvidia.com/nim/reference/meta-llama-3_2-90b-vision-instruct) |
| `nvidia/nemotron-nano-12b-v2-vl` | [docs.api.nvidia.com](https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-nano-12b-v2-vl) |
| `nvidia/llama-3.1-nemotron-nano-8b-v1` | [docs.api.nvidia.com](https://docs.api.nvidia.com/nim/reference/nvidia-llama-3_1-nemotron-nano-8b-v1) |
| `meta/llama-3.2-3b-instruct` | [docs.api.nvidia.com](https://docs.api.nvidia.com/nim/reference/meta-llama-3_2-3b-instruct) |

Notes on short names: `nvidia/nemotron-3-ultra` and `nvidia/nemotron-3-super` are the
served model IDs used in NIM API calls; the full parameter-count identifiers
(e.g. `nvidia/nemotron-3-ultra-550b-a55b`) appear in docs and checkpoint names only.
`nvidia/llama-3.3-nemotron-super-49b-v1.5` (released 2025-07-25) is the current
recommended version, superseding v1 with additional RL/DPO training stages.

### Testing

- `tests/test_nvidia_nim_context.py` — 54 tests covering all 30 previously-
  unrecognized families, all stale-value corrections, longest-key invariants, and
  the nvidia curated list.
- `tests/test_model_context.py` — updated 3 existing assertions for corrected deepseek
  values.

All tests pass.

## Target branch

- [x] This PR targets **`dev`**, not `main`.

## Linked Issue

Fixes # <!-- [add upstream issue number before filing] -->

## Type of Change

- [ ] Bug fix (non-breaking, fixes a confirmed issue)
- [x] New feature (non-breaking, adds new behaviour)
- [ ] Breaking change (changes or removes existing behaviour)
- [ ] Refactor / cleanup (behaviour unchanged)
- [ ] Documentation only
- [ ] CI / tooling / configuration

## Checklist

- [x] I searched [open issues](https://github.com/pewdiepie-archdaemon/odysseus/issues) and [open PRs](https://github.com/pewdiepie-archdaemon/odysseus/pulls); this is not a duplicate.
- [x] This PR targets `dev`
- [x] My changes are limited to the scope described above; no unrelated refactors or whitespace changes mixed in.
- [ ] **I am not an LLM agent submitting a bulk PR.** I reviewed and tested this change personally before submitting.

### How to Test

1. Configure `integrate.api.nvidia.com/v1` as an API endpoint with a NIM API key.
2. Select any previously-unrecognized model (e.g. `deepseek-ai/deepseek-v4-pro`,
   `stepfun-ai/step-3.5-flash`, `moonshotai/kimi-k2.6`).
3. Start an agent session. Confirm the log shows the correct context window (not
   `known=False`) and that `agent_input_token_budget` auto-scales to ~85% of the model's
   actual ISL rather than staying at 6000.
4. Open the model picker on a NIM endpoint. Confirm the Nemotron/DeepSeek flagship
   models appear first rather than in raw alphabetical order.
5. Run `pytest tests/test_nvidia_nim_context.py tests/test_model_context.py -q`.

---

## Filing Notes

- Four commits (includes a revert). Squash to three before filing if preferred.
- Branch: `feat/nvidia-nim-support` — built from `upstream-mirror`.
- **File upstream issue first.** Add the upstream issue number to `Fixes #` above.
- All curated list model IDs verified against NVIDIA NIM documentation
  (docs.api.nvidia.com/nim/reference/). Citations in table above.

## Visual / UI changes

Model picker ordering changes for the NIM endpoint: flagship models appear first.
No layout, DOM, or CSS changes.
