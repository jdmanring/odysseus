# Upstream Issue Draft: fix-nvidia-native-tool-calling

**File on:** `pewdiepie-archdaemon/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/fix-nvidia-native-tool-calling.md`
**Branch:** `fix/nvidia-native-tool-calling`
**Type:** Bug

---

## Title

`[Agent] NVIDIA NIM models receive no tool schemas — missing from _API_HOSTS and _model_supports_tools`

---

## Body

**Install method:** Docker / manual Python

**OS / device:** Any

**Steps to reproduce:**

1. Add an NVIDIA NIM endpoint (`integrate.api.nvidia.com`) in Settings → Endpoints.
2. Select a NIM model that supports tool calling (e.g., `meta/llama-3.3-70b-instruct`).
3. Run an agent task that requires tool use (search, file operations, etc.).
4. Observe: no tools are offered to the model; the agent runs without tool schemas injected.

**Root cause:**

Two gaps in `src/agent_loop.py` (or equivalent):

1. `_API_HOSTS` does not include `integrate.api.nvidia.com`. The host check that gates tool-call schema injection does not recognize NIM endpoints, so the code path that builds and sends tool schemas is never reached.

2. `_model_supports_tools` (or equivalent tool-compatibility check) does not include `"nemotron"` as a keyword, so Nemotron-family models that do support tool calling are excluded.

NVIDIA NIM supports OpenAI-compatible tool calling for all its hosted language models. The API accepts the standard `tools` parameter in the request body and returns `tool_calls` in the response exactly as OpenAI does.

**Expected:** When a NIM endpoint is configured and the selected model supports tool calls, tool schemas are injected and tool calls are processed correctly.

**Affected files:** `src/agent_loop.py` — `_API_HOSTS`, `_model_supports_tools`
