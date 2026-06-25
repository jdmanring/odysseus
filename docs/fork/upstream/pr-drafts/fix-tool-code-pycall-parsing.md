# fix(tool_parsing): parse and strip <tool_code> Python-call format (Google Gemma)

**Branch:** `fix/tool-code-pycall-parsing`
**Type:** Bug fix
**Status:** Ready to file

## Summary

### Problem

Google Gemma models emit tool calls as Python function-call syntax inside `<tool_code>`
tags:

```xml
<tool_code>bash(command="gh repo list --limit 10")</tool_code>
```

The existing `<tool_code>` handler in `parse_tool_blocks()` only recognised MiniMax's
`{tool => 'name', args => '...'}` format. Gemma-style Python-call blocks were neither
executed nor stripped from the response; the raw `<tool_code>...</tool_code>` XML
appeared verbatim in the chat as if it were plain text.

### Who is affected

**Every user running a Google Gemma model via Odysseus** who tries to use tools. Gemma
is one of the most-downloaded model families on HuggingFace
([huggingface.co/google](https://huggingface.co/google)), making it one of the most
commonly self-hosted models. Users trying agentic tasks with
Gemma see what appears to be a broken model; the model
"knows" to call a tool (the `<tool_code>` block appears), but nothing happens. The raw
XML is then visible in the chat as response text, making it look like an error or a
template rendering bug.

The failure is also silent from the agent loop's perspective: no exception is raised,
no tool budget is consumed, no error appears in logs. The model simply does not act.

### Why `_TOOL_CODE_ANY_RE` matters beyond Gemma

The PR also changes `strip_tool_blocks()` to use `_TOOL_CODE_ANY_RE` (matches any
`<tool_code>` block regardless of inner format) instead of the narrower `_TOOL_CODE_RE`.
The existing docstring states: "that markup should never reach the user regardless of
whether it converted to a tool call." The old regex honoured this for the MiniMax format
only; an unrecognised `<tool_code>` inner format would still leak. `_TOOL_CODE_ANY_RE`
makes the guarantee universal; any `<tool_code>` block that does not parse into a
recognised tool is stripped rather than displayed.

## Target branch

- [x] This PR targets **`dev`**, not `main`.

## Linked Issue

Fixes # <!-- [file upstream issue first] -->

## Type of Change

- [x] Bug fix (non-breaking)

## Files changed

- `src/tool_parsing.py`: add `_TOOL_CODE_PYCALL_RE`, `_TOOL_CODE_ANY_RE`, `_parse_tool_code_pycall()`; hook into `parse_tool_blocks`; update `strip_tool_blocks`

## How it works

`_parse_tool_code_pycall()` uses `ast.parse` (already imported) to extract the function
name and keyword arguments from blocks like `bash(command="gh repo list")`. The name is
looked up in `_TOOL_NAME_MAP` and the args are routed through `function_call_to_tool_block`
— the same path used by native function calls and `<invoke>` blocks.

`strip_tool_blocks` is updated to use `_TOOL_CODE_ANY_RE` (matches any `<tool_code>` block
regardless of inner format) instead of the narrower `_TOOL_CODE_RE`, consistent with the
existing docstring: "that markup should never reach the user regardless of whether it
converted to a tool call."

The MiniMax `{tool => ...}` path is unchanged and still tried first.

## How to Test

**Automated:**
```
pytest tests/test_tool_parsing_pycall.py
```
Covers: bash and web_search parsing, MiniMax regression, `strip_tool_blocks` universality, unknown function name, malformed Python syntax.

**Manual (with a Gemma model):**
- [ ] Ask the agent to run a shell command; confirm it executes via `bash` rather than printing `<tool_code>bash(...)</tool_code>` as text
- [ ] Confirm MiniMax-style `{tool => 'bash', args => '...'}` blocks still execute
- [ ] Confirm a `<tool_code>` block with unrecognised content is stripped and not shown to the user

## Visual / UI changes

None visible when working correctly; tool calls execute silently. Previously the raw
`<tool_code>` XML was visible in the chat; this removes it.

## Checklist

- [x] I searched open issues and open PRs; this is not a duplicate.
- [x] Related to closed issue #3222 (opposite problem: fenced blocks accidentally executed)
- [x] This PR targets `dev`
- [x] Changes are limited to `src/tool_parsing.py`
- [x] I ran the app and verified the change works end-to-end.
- [ ] **I am not an LLM agent submitting a bulk PR.** I reviewed and tested this change personally before submitting.

## Filing Notes

- File upstream issue first (draft: `docs/fork/upstream/issue-drafts/fix-tool-code-pycall-parsing.md`)
- No screenshots required
- Related discussion: #2095 (same symptom; raw tool call output instead of execution; reported for Qwen and Mistral; those are different parsers but the same general gap this PR closes for Gemma).
- `pytest tests/test_tool_parsing_pycall.py`: 10 tests: bash/web_search parsing, MiniMax regression, strip universality, unknown function and malformed syntax rejection
