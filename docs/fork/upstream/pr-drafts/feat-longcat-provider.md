# PR Draft: feat/longcat-provider → pewdiepie-archdaemon/odysseus:dev

**Branch:** `jdmanring/odysseus:feat/longcat-provider`
**Issue:** [#58](https://github.com/jdmanring/odysseus/issues/58) (fork tracking)
**Status:** Ready to file

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

### API compatibility notes

LongCat exposes a standard OpenAI-compatible chat completions endpoint.
No protocol quirks requiring special handling were found in the documentation.
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

- [x] I searched [open issues](https://github.com/pewdiepie-archdaemon/odysseus/issues) and [open PRs](https://github.com/pewdiepie-archdaemon/odysseus/pulls); this is not a duplicate.
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

---

## Filing Notes

- Single commit (`71deb0e4`). No squash needed.
- Branch: `feat/longcat-provider` — built from `upstream-mirror`.
- **File upstream issue first.** Add the upstream issue number to `Fixes #` above.
- LongCat is Meituan's API service. API reference: https://longcat.chat/platform/docs/APIDocs.html

## Visual / UI changes

- Provider quick-add dropdown gains a "LongCat" entry.
- Endpoint label displays "LongCat" instead of raw hostname for `longcat.chat` URLs.
- Model picker shows LongCat cat icon for the provider.
