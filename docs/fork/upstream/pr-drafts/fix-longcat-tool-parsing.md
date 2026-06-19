# PR Draft: fix/longcat-tool-parsing

**Fork issue:** [#38](https://github.com/jdmanring/odysseus/issues/38)
**Branch:** `fix/longcat-tool-parsing` (from `upstream-mirror`)
**Target:** `pewdiepie-archdaemon/odysseus:dev`
**Status:** Ready to file

---

## Proposed title

`fix(tool_parsing): add parser and strip support for Meituan LongCat tool_call format`

---

## Summary

### Problem

Odysseus has no pattern for this format, so tool calls from LongCat models are silently
ignored and the raw XML is displayed to the user as response text.

Two distinct variants appear in the wild:

**Variant A (JSON object)** ([LongCat-2.0-Preview model card](https://huggingface.co/meituan-longcat/LongCat-2.0-Preview)):
```xml
<longcat_tool_call>{"name": "fn_name", "arguments": {"key": "value"}}</longcat_tool_call>
```

**Variant B (tag pairs)** (observed in session; Vercel community also reports this variant — verify link before filing: `community.vercel.com/t/parsing-custom-xml-tool-calls-from-longcat-flash-models-in-vercel-ai-sdk/33601`):
```xml
<longcat_tool_call>fn_name
<longcat_arg_key>path</longcat_arg_key>
<longcat_arg_value>./index.vue</longcat_arg_value>
</longcat_tool_call>
```

### Solution

Adds `_LONGCAT_TOOL_CALL_RE` (Pattern 6 in `tool_parsing.py`) and
`_parse_longcat_tool_call()`:

- Variant A (JSON): parsed via `_parse_longcat_tool_call()`; `name` → tool type,
  `arguments` → JSON args string; goes through `function_call_to_tool_block()` for
  normalisation and tool name mapping, with a single-value fallback identical to the
  other parsers.
- Variant B (tag pairs): not executed. `_parse_longcat_tool_call()` returns `None`
  immediately for non-JSON content; the tag-pair format is stripped from display by
  `strip_tool_blocks()` but produces no tool invocation.

`strip_tool_blocks()` gains the corresponding cleanup regex so both variants are removed
from displayed text regardless of whether they were executed.

`_model_supports_tools()` in `agent_loop.py` gains "longcat" as a known keyword so the
agent loop sends tool schemas to LongCat models.

---

## Target branch

- [x] This PR targets **`dev`**, not `main`. All PRs land in `dev`; `main` is curated by the maintainer at each release.

## Linked Issue

Fixes # <!-- [file upstream issue first; see issue-drafts/fix-longcat-tool-parsing.md] -->

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

1. Configure a LongCat endpoint as an OpenAI-compatible provider in Settings → Providers:
   - **OpenRouter:** model ID `meituan/longcat-flash-chat`
   - **Direct API:** base URL `https://api.longcat.chat/openai/v1/` with a Meituan API key
2. Send a prompt that triggers a tool call (e.g. "read the file ./index.vue" with the
   file tool enabled).
3. Confirm the tool executes and the result is returned to the model; the raw
   `<longcat_tool_call>` block should not appear in the chat response.
4. Variant B (tag-pair format) is stripped from display but not executed —
   `strip_tool_blocks()` removes the raw tags. No behavioral test is possible without
   a model that emits this format; it is stripped silently regardless of whether the
   tool name is recognized.
5. Confirm `strip_tool_blocks()` removes the block when the tool is not executed
   (i.e. send a prompt that produces a `<longcat_tool_call>` block but do not execute it;
   confirm the raw XML does not appear in the displayed response).

**Unit tests:** `pytest tests/test_longcat_tool_parsing.py`: 13 tests covering
Variant A (JSON object), Variant B (tag-pair), unknown-name pass-through (intentional
behavioral difference from the pycall parser; longcat passes unknown names through as
raw ToolBlocks rather than filtering them), no-args rejection, malformed JSON
no-crash, and `strip_tool_blocks` for both variants. No network access required.

---

## Filing Notes

- **File upstream issue first**: draft in `docs/fork/upstream/issue-drafts/fix-longcat-tool-parsing.md`. Add the issue number to `Fixes #` above before opening the PR.
- One commit, no squash needed.
- This PR coexists cleanly with `fix/tool-code-pycall-parsing` (Pattern 5, `<tool_code>`
  blocks). The two parsers handle different formats and are independent.

## Visual / UI changes

None; no HTML, CSS, or DOM-writing JS was changed.
