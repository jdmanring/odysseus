# PR Draft: fix/google-compat-toolcalls

**Fork issue:** [#39](https://github.com/jdmanring/odysseus/issues/39)
**Branch:** `fix/google-compat-toolcalls` (from `upstream-mirror`)
**Target:** `pewdiepie-archdaemon/odysseus:dev`
**Status:** Ready to file

---

## Proposed title

`fix(llm): handle camelCase toolCalls key in Google OpenAI-compat streaming response`

---

## Summary

### Problem

Google's OpenAI-compatibility endpoint (`generativelanguage.googleapis.com/v1beta/openai/`)
sends tool call deltas under the camelCase key `"toolCalls"` rather than the OpenAI-spec
snake_case `"tool_calls"`. The streaming parser in `llm_core.py` only reads
`delta.get("tool_calls")`, so tool calls from Google models via the OpenAI-compat path
are silently dropped; the model responds as if no tools are available even when schemas
were sent.

Google's OpenAI-compat streaming format has multiple known deviations from the OpenAI spec.
A related thread in Google's developer forum ([Gemini OpenAI compatibility issue with
tool_call + streaming](https://discuss.ai.google.dev/t/gemini-openai-compatibility-issue-with-tool-call-streaming/59886),
January 2025, unresolved as of November 2025) documents a missing `index` field in streaming
tool call objects — a different structural deviation, same endpoint. The camelCase `toolCalls`
key divergence documented here was observed directly in streaming response inspection and is
not currently tracked in a public upstream issue.

### Solution

Two targeted fixes in `stream_llm()` in `src/llm_core.py`:

1. **Early-exit guard**: `_delta_has_output` check adds `or _delta0.get("toolCalls")`
   so chunks whose only content is a `toolCalls` delta are not mistakenly treated as
   empty and skipped.

2. **Accumulator loop**: `delta.get("tool_calls") or delta.get("toolCalls") or []`
   ensures both key spellings are consumed by the tool call accumulation logic.

No changes to any other path. The snake_case key remains the primary check; camelCase is
an explicit fallback that fires only when `tool_calls` is absent.

### ROADMAP alignment

The ROADMAP lists "Provider setup/probing audit for Anthropic, Gemini, Groq, xAI,
OpenRouter, OpenAI, and DeepSeek" as a high-priority item. Gemini via the OpenAI-compat
path is currently broken for tool use due to this key mismatch; tools appear available
in the UI but never execute. This fix makes the compat path functional for Gemini tool
use without touching any other provider.

---

## Target branch

- [x] This PR targets **`dev`**, not `main`. All PRs land in `dev`; `main` is curated by the maintainer at each release.

## Linked Issue

Fixes # <!-- [file upstream issue first; see issue-drafts/fix-google-compat-toolcalls.md] -->

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
- [x] I actually ran the app (`docker compose up` or `uvicorn app:app`) and verified the change works end-to-end. Type-checks and unit tests are not enough.
- [ ] **I am not an LLM agent submitting a bulk PR.** I reviewed and tested this change personally before submitting.

## How to Test

1. Configure a Google model via Settings → Providers → OpenAI-Compatible, pointing to
   `https://generativelanguage.googleapis.com/v1beta/openai/` with a Gemini model that
   supports function calling (e.g. `gemini-2.0-flash`, `gemini-1.5-pro`).
2. Enable one or more tools in the chat (e.g. web search, file read).
3. Send a prompt that requires a tool call.
4. Confirm the tool executes and the agent loop proceeds; before this fix, the tool call
   would be silently ignored and the agent would respond as if no tool schemas were sent.

**Without a Google API key:** inspect the streaming response from the Google endpoint
directly and confirm `toolCalls` (camelCase) is present in the delta chunks for models
that emit tool calls.

**Static contract tests (no API key, no network):**

- [x] `pytest tests/test_google_compat_toolcalls.py`: 4 tests assert that both
  camelCase fallback sites exist in `src/llm_core.py`: the `_delta_has_output` guard
  (`_delta0.get("toolCalls")`), the accumulator loop (`delta.get("toolCalls")`), and
  that `get("toolCalls")` appears at least twice in the source.

---

## Filing Notes

- **File upstream issue first**: draft in `docs/fork/upstream/issue-drafts/fix-google-compat-toolcalls.md`. Add the issue number to `Fixes #` above before opening the PR.
- One commit, no squash needed. Change is 3 lines in `src/llm_core.py`.
- This is a pure OpenAI-compat path fix and does not affect native Google API usage
  (which is a separate provider path not yet implemented in Odysseus).
- ROADMAP alignment: "Provider setup/probing audit for Anthropic, Gemini, Groq, xAI, OpenRouter, OpenAI, and DeepSeek"; mention this in the PR body.
- The Google developer forum link (`https://discuss.ai.google.dev/t/gemini-openai-compatibility-issue-with-tool-call-streaming/59886`) resolves and is active (verified 2026-06-18). The thread covers a different deviation (missing `index` field) — it is cited as context for Google's pattern of compat endpoint spec divergence, not as a direct source for the camelCase key bug.

## Visual / UI changes

None; no HTML, CSS, or DOM-writing JS was changed.
