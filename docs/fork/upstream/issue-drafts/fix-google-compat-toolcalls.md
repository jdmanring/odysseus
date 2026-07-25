# Upstream Issue Draft: fix-google-compat-toolcalls

**File on:** `odysseus-dev/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/fix-google-compat-toolcalls.md`
**Branch:** `fix/google-compat-toolcalls`
**Type:** Bug

---

## Title

`[LLM] Google OpenAI-compat endpoint sends camelCase "toolCalls": tool calls silently dropped`

---

## Body

**Install method:** Docker / manual Python

**OS / device:** Any

**Steps to Reproduce:**
1. Add a Google model via Settings -> Providers -> OpenAI-Compatible. Base URL: `https://generativelanguage.googleapis.com/v1beta/openai/`. Model: `gemini-2.0-flash` or `gemini-1.5-pro`.
2. Enable at least one tool in the chat (e.g. web search).
3. Send a prompt that should trigger a tool call.
4. Observe the response.

**Expected:** The tool executes and the model uses the result.

**Actual:** The tool call is silently dropped. The model responds as if no tool schemas were provided, even when schemas were sent in the request.

**Root cause:**

Google's OpenAI-compatibility endpoint (`generativelanguage.googleapis.com/v1beta/openai/`) deviates from the OpenAI streaming spec: it sends tool call deltas under the camelCase key `"toolCalls"` instead of snake_case `"tool_calls"`.

Odysseus's `stream_llm()` in `src/llm_core.py` reads only `delta.get("tool_calls")`. When the key is `"toolCalls"`, the result is `None`, the accumulator loop receives an empty list, and the tool call is never processed.

This is a documented deviation on Google's side and has not been corrected in their API. All other OpenAI-compat providers use the correct snake_case key; only Google's endpoint is affected.

**Proposed fix:** Two targeted fixes in `stream_llm()`: (1) the `_delta_has_output` early-exit guard gains `or _delta0.get("toolCalls")` to prevent camelCase-only chunks from being skipped; (2) the accumulator loop uses `delta.get("tool_calls") or delta.get("toolCalls") or []` to consume both spellings. Three lines changed in `src/llm_core.py`.
