# PR Draft: fix/nvidia-native-tool-calling → pewdiepie-archdaemon/odysseus:dev

**Branch:** `jdmanring/odysseus:fix/nvidia-native-tool-calling`
**Fork issue:** [#60](https://github.com/jdmanring/odysseus/issues/60) (open)
**Status:** Single clean commit (`116bb913`). File upstream issue first, fill in `Fixes #___`, then open PR.

---

## Upstream PR title

`fix(agent): NVIDIA NIM models receive no native tool schemas`

---

## Summary

### Problem

NVIDIA NIM's OpenAI-compatible endpoint (`https://integrate.api.nvidia.com/v1`) is not
listed in `_API_HOSTS`. The expression that gates native tool calling is:

```python
_is_api_model = any(h in endpoint_url for h in _API_HOSTS) or _model_supports_tools
```

When neither arm matches, `_is_api_model` is `False`. The agent then:

1. Sends fenced-block tool descriptions in the system prompt instead of OpenAI function
   schemas in the `tools` field.
2. Routes tool results through `untrusted_context_message()` as `role: "user"` instead
   of `role: "tool"` with a `tool_call_id`.

NVIDIA NIM exposes a fully OpenAI-compatible function-calling API. Both Nemotron-Ultra
and Nemotron-Super are documented to support function calling. Sending fenced-block
descriptions instead of native schemas makes tool calls unreliable and — for models
that parse JSON function calls natively — produces malformed output.

The `_model_supports_tools` keyword list includes many model families but not
`"nemotron"`. Nemotron model names (`nvidia/llama-3.1-nemotron-ultra-253b-v1`,
`nvidia/nemotron-3-super`) contain no listed keyword, so the belt-and-suspenders path
also fails.

### Fix

**`src/agent_loop.py` — `_API_HOSTS`:**

```python
"integrate.api.nvidia.com",   # NIM — OpenAI-compatible function calling
```

Substring-match against the full endpoint URL. `integrate.api.nvidia.com` is the only
documented NIM API hostname; self-hosted NIM deployments use localhost or a custom host
and are already covered by the `"localhost"` and `"127.0.0.1"` entries.

**`src/agent_loop.py` — `_model_supports_tools` keyword tuple:**

```python
# NVIDIA NIM — Nemotron-native model names contain no other listed keyword.
# Belt-and-suspenders with the integrate.api.nvidia.com host entry above for
# non-NIM deployments of Nemotron weights.
"nemotron",
```

This covers Nemotron weights served via any OpenAI-compatible host (e.g. vLLM
on a local GPU cluster), where the host entry alone would not apply.

### Scope

One file changed: `src/agent_loop.py` (+5 lines). No tests exist for `_API_HOSTS`
membership in the current test suite; the affected code path requires a live NIM
API key to exercise end-to-end.

---

## How to Test

1. Configure `https://integrate.api.nvidia.com/v1` as an API endpoint with a NIM API key.
2. Select `nvidia/llama-3.1-nemotron-ultra-253b-v1` or any Nemotron model.
3. Enable Agent mode with at least one tool (e.g. web search or shell access).
4. Send a message that requires tool use.
5. **Expected (after fix):** the request payload contains a `tools` array with JSON
   function schemas. The model returns a `tool_calls` response. Tool results are sent
   as `role: "tool"` messages.
   **Before this fix:** the system prompt contains fenced `<tool_description>` blocks.
   The model's tool invocations are parsed from text, not structured JSON.

6. Repeat step 4 with a Nemotron model served via a self-hosted vLLM instance at a
   custom hostname — confirm `_model_supports_tools` picks up `"nemotron"` and enables
   native schemas regardless of the host URL.

---

## Filing Notes

- Single commit (`116bb913`). No squash needed.
- Branch: `fix/nvidia-native-tool-calling` — built from `upstream-mirror`.
- **File upstream issue first.** Add the upstream issue number to `Fixes #___` before opening.
- PR targets `pewdiepie-archdaemon/odysseus:dev`.
- This fix is a subset of the broader NVIDIA NIM support in `feat/nvidia-nim-support`
  (context windows, curated model list). If both PRs are filed, this one should be noted
  as the tool-calling companion to that PR. They are independent and can merge in any order.

## Visual / UI changes

None. Backend-only change.

## Target branch

- [x] This PR targets **`dev`**, not `main`.

## Linked Issue

Fixes # <!-- [add upstream issue number before filing] -->

## Type of Change

- [x] Bug fix (non-breaking, fixes a confirmed issue)
- [ ] New feature (non-breaking, adds new behaviour)
- [ ] Breaking change (changes or removes existing behaviour)
- [ ] Refactor / cleanup (behaviour unchanged)
- [ ] Documentation only
- [ ] CI / tooling / configuration

## Checklist

- [x] I searched [open issues](https://github.com/pewdiepie-archdaemon/odysseus/issues) and [open PRs](https://github.com/pewdiepie-archdaemon/odysseus/pulls); this is not a duplicate.
- [x] This PR targets `dev`
- [x] My changes are limited to the scope described above; no unrelated refactors or whitespace changes mixed in.
- [ ] **I am not an LLM agent submitting a bulk PR.** I reviewed and tested this change personally before submitting.
