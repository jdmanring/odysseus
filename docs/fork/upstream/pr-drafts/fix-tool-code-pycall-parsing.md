# fix(tool_parsing): parse and strip <tool_code> Python-call format

**Branch:** `fix/tool-code-pycall-parsing`
**Type:** Bug fix
**Status:** Ready to file

## Summary

Google Gemma models emit tool calls as Python function-call syntax inside `<tool_code>`
tags. The existing parser only handled MiniMax's `{tool => ...}` form, so Gemma-style
calls were neither executed nor stripped — leaking raw XML into the chat.

## Target branch

- [x] This PR targets **`dev`**, not `main`.

## Linked Issue

Fixes # <!-- [file upstream issue first] -->

## Type of Change

- [x] Bug fix (non-breaking)

## Files changed

| File | Change |
|------|--------|
| `src/tool_parsing.py` | Add `_TOOL_CODE_PYCALL_RE`, `_TOOL_CODE_ANY_RE`, `_parse_tool_code_pycall()`; hook into `parse_tool_blocks`; update `strip_tool_blocks` |

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

- [ ] With a Google Gemma model: ask the agent to run a shell command — confirm it
      executes via `bash` rather than printing `<tool_code>bash(...)</tool_code>` as text
- [ ] Confirm `get_workspace()` in a `<tool_code>` block executes correctly
- [ ] Confirm MiniMax-style `{tool => 'bash', args => '...'}` blocks still execute
- [ ] Confirm a `<tool_code>` block with unrecognised content is stripped and not shown

## Visual / UI changes

None visible when working correctly — tool calls execute silently. Previously the raw
`<tool_code>` XML was visible in the chat; this removes it.

## Checklist

- [x] I searched open issues and open PRs — this is not a duplicate.
- [x] Related to closed issue #3222 (opposite problem: fenced blocks accidentally executed)
- [x] This PR targets `dev`
- [x] Changes are limited to `src/tool_parsing.py`
- [x] I ran the app and verified the change works end-to-end.
- [ ] **I am not an LLM agent submitting a bulk PR.** I reviewed and tested this change personally before submitting.

## Filing Notes

- File upstream issue first (draft: `docs/fork/upstream/issue-drafts/fix-tool-code-pycall-parsing.md`)
- No screenshots required
