# Upstream Issue Draft: fix-longcat-tool-parsing

**File on:** `pewdiepie-archdaemon/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/fix-longcat-tool-parsing.md`
**Branch:** `fix/longcat-tool-parsing`
**Type:** Bug

---

## Title

`[Tool Parsing] LongCat (Meituan) tool_call format not parsed — tool calls silently ignored`

---

## Body

**Install method:** Docker / manual Python

**OS / device:** Any

**Steps to Reproduce:**
1. Configure a LongCat endpoint as an OpenAI-compatible provider in Settings → Providers:
   - **OpenRouter:** model ID `meituan/longcat-flash-chat`
   - **Direct API:** base URL `https://api.longcat.chat/openai/v1/` with a Meituan API key
2. Enable at least one tool (e.g. web search or file read).
3. Send a prompt that should trigger a tool call (e.g. "search for recent news about X").
4. Observe the response.

**Expected:** The tool executes and the agent loop uses the result to formulate a response.

**Actual:** The tool call is silently ignored. The raw `<longcat_tool_call>...</longcat_tool_call>` XML block appears in the chat response as plain text, or the model responds as if no tools are available.

**Root cause:**

Odysseus's `parse_tool_blocks()` in `src/tool_parsing.py` recognises five tool call formats (JSON `tool_calls`, `<tool_call>` XML, `<invoke>` XML, DeepSeek DSML, and `<tool_code>` Python-call) but has no pattern for the LongCat format.

LongCat models emit two variants:

- **Variant A (JSON):** `<longcat_tool_call>{"name": "fn", "arguments": {"k": "v"}}</longcat_tool_call>`
- **Variant B (tag-pairs):** `<longcat_tool_call>fn_name\n<longcat_arg_key>k</longcat_arg_key>\n<longcat_arg_value>v</longcat_arg_value>\n</longcat_tool_call>`

Neither variant is matched, so tool calls from LongCat models never execute. Additionally, `strip_tool_blocks()` does not strip unexecuted `<longcat_tool_call>` blocks, so the raw XML leaks into displayed responses.

**PR:** Adds `_LONGCAT_TOOL_CALL_RE` and `_parse_longcat_tool_call()` to `parse_tool_blocks()`, integrates cleanup into `strip_tool_blocks()`, and adds "longcat" to `_model_supports_tools()` so the agent loop sends schemas to LongCat endpoints. Variant A (JSON) is parsed and executed; Variant B (tag-pairs) is stripped from display but not executed.
