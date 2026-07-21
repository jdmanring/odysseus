# PR Draft: feat/longcat-provider → odysseus-dev/odysseus:dev

**Branch:** `feat/longcat-provider`
**Issues:** [#58](https://github.com/jdmanring/odysseus/issues/58) (provider integration), [#61](https://github.com/jdmanring/odysseus/issues/61) (max_tokens + stream_options gaps)
**Status:** 3 commits — ready to file. File upstream issue first.

---

## Title

`feat(providers): add LongCat (Meituan) as a first-class provider`

---

## Summary

### Problem

LongCat — an OpenAI-compatible API from Meituan — is not recognized by Odysseus.
Users who type `https://api.longcat.chat/openai/v1` into the endpoint form get:

- Hostname (`api.longcat.chat`) used as the endpoint display name instead of "LongCat"
- No curated model list → model picker presents any available models alphabetically
  with no ordering
- No entry in `KNOWN_CONTEXT_WINDOWS` → `LongCat-2.0-Preview` (1M-token context)
  falls through to the `DEFAULT_CONTEXT=128000` floor with `known=False`, causing
  `budget_context_for_model` to return 0 and `agent_input_token_budget` to lock at
  the 6000-token sentinel — destroying 99% of the available context for agent sessions
- No quick-add dropdown entry → users must type the URL manually
- No `/setup longcat` slash-command alias

### What changed

**`src/llm_core.py`:**
- `_detect_provider`: `longcat.chat` → `"longcat"`
- `_provider_label`: `longcat.chat` → `"LongCat"`

**`src/model_context.py` — `KNOWN_CONTEXT_WINDOWS`:**
- `'longcat': 1048576` — LongCat-2.0-Preview exposes a 1,048,576-token context window.
  Source: https://longcat.chat/platform/docs/APIDocs.html

**`routes/model_routes.py`:**
- `_PROVIDER_CURATED["longcat"]`: `["LongCat-2.0-Preview"]` — single model as of
  2026-06-19. Source: https://longcat.chat/platform/docs/APIDocs.html
- `_HOST_TO_CURATED`: `("longcat.chat", "longcat")`

**`static/js/providers.js`:**
- `_PROVIDERS`: `/longcat/i` → cat SVG icon (silhouette with pointed ears)
- `_ENDPOINT_LABELS`: `/(^|\.)longcat\.chat$/i` → `"LongCat"`

**`static/index.html`:**
- Quick-add provider dropdown: `LongCat` entry pointing to
  `https://api.longcat.chat/openai/v1`

**`static/js/modelPicker.js`:**
- `_PROVIDER_NAMES`: `'longcat': 'LongCat'`

**`static/js/slashCommands.js`:**
- `SETUP_PROVIDER_URLS`: `longcat: { name: 'LongCat', url: 'https://api.longcat.chat/openai/v1' }`
- `SETUP_PROVIDER_NAMES`: `'longcat'` appended

**`src/agent_loop.py` — `_API_HOSTS`:**

```python
"api.longcat.chat",  # belt-and-suspenders: ensures native schemas even for
                     # future LongCat model names that may not contain "longcat"
```

**`src/llm_core.py` — `_PROVIDER_DEFAULT_MAX_OUTPUT` (new table):**

```python
_PROVIDER_DEFAULT_MAX_OUTPUT: dict[str, int] = {
    "longcat": 131072,  # API default 32 768; documented max 131 072
}
```

Applied at all three payload-building sites in `llm_core.py` via:

```python
_effective_max_tokens = max_tokens if max_tokens and max_tokens > 0 \
    else _PROVIDER_DEFAULT_MAX_OUTPUT.get(provider, 0)
if _effective_max_tokens > 0:
    tok_key = "max_completion_tokens" if _uses_max_completion_tokens(model) \
        else "max_tokens"
    payload[tok_key] = _effective_max_tokens
```

This replaces the previous unconditional `if max_tokens and max_tokens > 0` guard,
which meant Odysseus sent no `max_tokens` when the caller passed `0` (the "let API
decide" sentinel) — causing the LongCat API to apply its 32 768-token default and
truncate long responses mid-output.

**`src/llm_core.py` — `stream_options` exclusion:**

```python
if provider not in {"openrouter", "groq", "longcat"}:
    payload["stream_options"] = {"include_usage": True}
```

LongCat's documented parameter list (`max_tokens`, `temperature`, `top_p`, `stream`,
`tools`, `tool_choice`) does not include `stream_options`. Sending it caused HTTP
400/422 or a malformed streaming response. LongCat added to the existing exclusion set.

### API compatibility notes

LongCat exposes a standard OpenAI-compatible chat completions endpoint with two
documented quirks: a 32 768-token API default for `max_tokens` (ceiling 131 072), and
no support for `stream_options`. Both are handled by the additions above.

The model name `LongCat-2.0-Preview` is mixed-case and must be sent exactly
as documented — the curated list entry preserves this casing.

LongCat does not expose a `/v1/models` endpoint, so model discovery relies
on the curated list. This is consistent with how other single-model providers
(e.g. some Kimi endpoints) are handled in the codebase.

### Source verification

All claims are sourced from the LongCat platform documentation:
https://longcat.chat/platform/docs/APIDocs.html

| Fact | Source |
|------|--------|
| API base URL: `https://api.longcat.chat/openai/v1` | LongCat API docs |
| Model name: `LongCat-2.0-Preview` | LongCat API docs |
| Context window: 1,048,576 tokens | LongCat API docs |
| No `/v1/models` endpoint | LongCat API docs |

### Testing

`tests/test_longcat_provider.py` (new, 11 tests):

| Class | Tests |
|-------|-------|
| `TestLongCatDetect` | API host detected; apex detected; lookalike rejected; domain-in-path rejected |
| `TestLongCatLabel` | API host → "LongCat"; apex → "LongCat" |
| `TestLongCatCurated` | URL matches curated key; Preview model in list; list is non-empty |
| `TestLongCatContextWindow` | Direct lookup returns 1048576; namespaced form resolves |

All 11 tests pass.

The `_PROVIDER_DEFAULT_MAX_OUTPUT` table and stream_options exclusion are in `llm_core.py`
payload-building code that requires a live API response to exercise end-to-end. Manual
testing procedure in "How to Test" below covers both gaps.

---

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

- [x] I searched [open issues](https://github.com/odysseus-dev/odysseus/issues) and [open PRs](https://github.com/odysseus-dev/odysseus/pulls); this is not a duplicate.
- [x] This PR targets `dev`
- [x] My changes are limited to the scope described above; no unrelated refactors or whitespace changes mixed in.
- [ ] **I am not an LLM agent submitting a bulk PR.** I reviewed and tested this change personally before submitting.

### How to Test

1. Open Settings → AI Defaults. Select the quick-add dropdown. Confirm "LongCat" appears.
2. Select LongCat from the dropdown. Confirm the endpoint name displays as "LongCat",
   not `api.longcat.chat`.
3. Open the model picker for a LongCat endpoint. Confirm `LongCat-2.0-Preview` appears
   at the top of the list.
4. Start an agent session with `LongCat-2.0-Preview`. Confirm the log shows
   `context=1048576, known=True` and `agent_input_token_budget` auto-scales rather
   than locking at 6000.
5. Type `/setup longcat` in the chat input. Confirm autocomplete offers the alias.
6. Run `pytest tests/test_longcat_provider.py -v`.

**Verifying the max_tokens fix (#61):**

7. Request a long output (e.g. "Write a 5000-word essay on..."). Confirm the response
   is not truncated at ~4000 words (the approximate 32 768-token output boundary).
8. In the raw request log, confirm `max_tokens: 131072` appears in the payload.

**Verifying the stream_options fix (#61):**

9. Enable streaming. Confirm no HTTP 400/422 error occurs.
10. In the raw request log, confirm `stream_options` does **not** appear in the payload
    for LongCat (it should appear for OpenAI, Anthropic, and other supported providers).

---

## Filing Notes

- Three commits (`212b5099` logo, `1b7f04b3` ordering fix, `fae6ae6d` max_tokens + stream_options + _API_HOSTS). Squash to one before filing if preferred; all are logically part of the same provider integration.
- Branch: `feat/longcat-provider` — built from `upstream-mirror`.
- **File upstream issue first.** Add the upstream issue number to `Fixes #` above.
- LongCat is Meituan's API service. API reference: https://longcat.chat/platform/docs/APIDocs.html

## Visual / UI changes

- Provider quick-add dropdown gains a "LongCat" entry.
- Endpoint label displays "LongCat" instead of raw hostname for `longcat.chat` URLs.
- Model picker shows LongCat cat icon for the provider.
