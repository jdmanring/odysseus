# Upstream Issue Draft: fix-tool-result-role

**File on:** `odysseus-dev/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/fix-tool-result-role.md`
**Branch:** `fix/tool-result-role`
**Type:** Bug

---

## Title

`[Agent] Text-based tool results injected as role=user: model re-reads them as user input, degrading multi-step agent quality`

---

## Body

**Install method:** Docker / manual Python

**OS / device:** Any

**Steps to Reproduce:**
1. Configure any OpenAI-compatible provider (Ollama, Gemini, LM Studio, etc.).
2. Start an agent session and give it a multi-step task that requires several sequential tool calls (e.g. "search for X, then read the top result, then summarize it").
3. Observe the model's behavior between tool rounds.

**Expected:** The model treats tool execution results as infrastructure-provided context and proceeds directly with the next step.

**Actual:** The model re-reads tool results as if the user sent them ("the user provided the following output…"), adds hedging turns, asks clarifying questions, or repeats work already done. Multi-step tasks take more rounds than necessary and produce lower-quality output.

**Logs / Error Output:**
No error logged. The symptom is degraded agent reasoning quality visible in the chat output.

**Additional context:** `_append_tool_results()` in `src/agent_loop.py` injects textual tool results with `"role": "user"`. On the non-native-tool path (text-encoded tool calls rather than OpenAI function-calling format), this makes tool results indistinguishable from actual user messages. Models trained on role-separated conversation formats interpret `role=user` content as user-injected input and respond accordingly.

The native tool path (`role=tool` for OpenAI function-calling format) is not affected by this bug: only the text-based fallback path.
