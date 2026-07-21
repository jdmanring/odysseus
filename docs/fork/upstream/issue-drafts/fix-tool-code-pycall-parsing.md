# Upstream Issue Draft: fix-tool-code-pycall-parsing

**File on:** `odysseus-dev/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/fix-tool-code-pycall-parsing.md`
**Branch:** `fix/tool-code-pycall-parsing`
**Type:** Bug fix

---

## Title

`[tool_parsing] <tool_code> blocks with Python function-call syntax are not parsed or stripped`

---

## Body

**Area:** Tool parsing / Agent loop

**Prerequisite context:** Issue #3222 (now closed) fixed the opposite problem — fenced code
blocks being accidentally executed as tool calls. Part of that fix introduced `skip_fenced`
for native function-calling models, which correctly prevents illustrative examples from
running. This issue is about a different gap in the same layer.

**Problem:**

`parse_tool_blocks` handles `<tool_code>` blocks in MiniMax-M2.5's
`{tool => 'name', args => '...'}` format via `_TOOL_CODE_RE`. However, Google Gemma models
emit tool calls as Python function-call syntax inside the same tag:

```
<tool_code>
bash(command="gh repo list")
</tool_code>
```

Because `_TOOL_CODE_RE` requires a `{...}` wrapper, Gemma-style calls are:
1. Not executed — the intended tool call never runs
2. Not stripped — the raw `<tool_code>` XML renders as visible text in the chat

The `_resolve_tool_blocks` comment explicitly states that `<tool_code>` appearing in text
content is always a real tool call, never illustrative. The Gemma format is a genuine call
the model couldn't emit on a structured channel, not user-facing prose.

**Fix:**

- Add `_TOOL_CODE_PYCALL_RE` matching the Python-call form
- Add `_parse_tool_code_pycall()` using `ast.parse` (already imported) to extract function
  name + kwargs and route through `_TOOL_NAME_MAP` / `function_call_to_tool_block`
- Hook into `parse_tool_blocks` after the existing MiniMax check
- Replace `_TOOL_CODE_RE` in `strip_tool_blocks` with `_TOOL_CODE_ANY_RE` — a broad
  pattern that strips any `<tool_code>` block regardless of inner format, consistent with
  the existing docstring: "that markup should never reach the user regardless of whether
  it converted to a tool call"

**Files:** `src/tool_parsing.py` only.

**Related:** Discussion #2095 reports the same symptom (agent outputs raw tool call markup instead of executing) with Qwen and Mistral models. Those involve different parser gaps; this issue covers the Gemma-specific `<tool_code>` Python-call format.
