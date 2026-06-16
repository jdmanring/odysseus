# PR Draft: fix/tool-result-role

**Fork issue:** [#4](https://github.com/jdmanring/odysseus/issues/4)
**Branch:** `fix/tool-result-role` (from `upstream-mirror`)
**Target:** `pewdiepie-archdaemon/odysseus:dev`
**Status:** Ready to file

---

## Proposed title

`fix(agent): use role=system for textual tool results; keep inline for Anthropic`

---

## Summary
### Problem

`_append_tool_results()` in `src/agent_loop.py` injects textual tool execution
results into the message history with `"role": "user"`:

```python
messages.append(
    {"role": "user", "content": f"[Tool execution results]\n\n{tool_output_text}"}
)
```

This affects the non-native-tool path; the branch taken when the model uses
text-encoded tool calls rather than the OpenAI native function-calling format.

With `role=user`, tool results are indistinguishable from actual user input. Models
trained on role-separated conversation formats interpret them as user-injected content
and respond accordingly.

### What this looks like to users

In practice, the model reads a tool result like `[Tool execution results]\n\nFile
contents: ...` as if the user typed it. The next model turn starts with phrases like:

- "The user has provided the following file contents. Based on this, I think..."
- "You've given me the search results. Here's what I found..."
- "Thank you for sharing this output. Let me analyse..."

The model adds a hedging acknowledgement turn rather than immediately acting on the
result. This is a direct consequence of training data format: models trained on
OpenAI-format conversations see `role=user` as user input — this is what the
[Chat Completions API specification](https://platform.openai.com/docs/api-reference/chat/create)
defines. The specification added `role=tool` (June 2023) precisely to distinguish
tool results from user input; injecting them as `role=user` mismatches the format the
model was trained on. One wasted round per tool call accumulates in multi-step tasks;
five tool calls in a session means five acknowledgement turns before any productive
work begins.

### Providers affected

This affects all providers that use the non-native tool path: every OpenAI-compatible
provider (Gemini via OpenAI compat, Ollama, LM Studio, llama-cpp-server, etc.) that
does not return structured `function_call` deltas. The native tool path (`role=tool`
messages from structured function calls) is unaffected.

### Fix

Two-part, provider-aware change.

**Part 1; `src/agent_loop.py`**

Change the injected role from `user` to `system`:

```python
messages.append(
    {"role": "system", "content": f"[Tool execution results]\n\n{tool_output_text}"}
)
```

For OpenAI-compatible providers, `role=system` messages appear inline at their
temporal position in the conversation, which is correct: each round's results
sit immediately after the assistant turn that triggered them. The model sees the
results as infrastructure-injected content, not user input.

**Part 2; `src/llm_core.py`**

`_build_anthropic_payload()` currently extracts all `role=system` messages into
the top-level Anthropic `system` prompt block. Doing this to tool results would
collapse all rounds' results into a single out-of-order block before the
conversation, breaking multi-round tool execution for Anthropic providers.

A targeted guard keeps tool results inline, routed as `role=user` in the
Anthropic payload (the only correct form for inline positional content on
Anthropic's API):

```python
if m.get("role") == "system" and (m.get("content") or "").startswith("[Tool execution results]"):
    # Must stay at its temporal position; do not extract to top-level system.
    chat_messages.append({"role": "user", "content": m["content"]})
elif m.get("role") == "system":
    system_parts.append(m.get("content") or "")
```

The `[Tool execution results]` prefix serves as a stable sentinel: it has been
present in all versions of this code path and is not user-generated content.

### Scope

This fix applies only to the text-based tool result path (the `else` branch in
`_append_tool_results`). The native tool path (`role=tool` messages from
OpenAI-format function calls) is unaffected; that path already uses the
correct role.

### Backward compatibility

Session databases contain historical messages with `role=user` and the
`[Tool execution results]` prefix. The guard in `_recent_context_for_retrieval`
that skips these records uses `startswith("[Tool execution results]")`: not a
role check; so old records continue to be correctly excluded regardless of
which role they carry.

## Checklist

- [x] I searched [open issues](https://github.com/pewdiepie-archdaemon/odysseus/issues) and [open PRs](https://github.com/pewdiepie-archdaemon/odysseus/pulls); this is not a duplicate.
- [x] This PR targets `dev`
- [x] My changes are limited to the scope described above; no unrelated refactors or whitespace changes mixed in.
- [x] I actually ran the app (`docker compose up` or `uvicorn app:app`) and verified the change works end-to-end. Type-checks and unit tests are not enough.
- [ ] **I am not an LLM agent submitting a bulk PR.** I reviewed and tested this change personally before submitting.

## How to Test
- Multi-round agent sessions with text-encoded tool calls: model correctly
  treats results as infrastructure context and proceeds without re-reading or
  hedging.
- Anthropic provider (Claude): multi-round tool execution completes correctly;
  results appear at their temporal position in the conversation, not collapsed
  at the top.
- OpenAI-compatible providers (Gemini, Ollama, etc.): no change in behavior for
  the native tool path; text-based path produces cleaner reasoning.

### Tests

**`tests/test_agent_loop.py`**: updated existing test to match the new role:
- `test_non_native_path_uses_system_role`: asserts the non-native fallback appends
  `role=system` (was `role=user`). Corrects the pre-existing upstream test that would
  have failed CI.
- `TestRecentContextForRetrieval` (6 new tests): verifies `_recent_context_for_retrieval`
  excludes old-format records (`role=user` + `[Tool execution results]` prefix,
  present in existing databases) and new-format records (`role=system`), includes only
  genuine user turns, and respects `max_user`.

**`tests/test_tool_result_role.py`** (new, 6 tests): verifies `_build_anthropic_payload`
inline routing; tool result system messages stay in `chat_messages` as `role=user` (not
extracted to `system_parts`), coexist with real system instructions, preserve their
temporal order across multiple agent rounds, and have their content preserved exactly.

### Files changed

- `src/agent_loop.py`: `_append_tool_results()` role change + comment update (4 insertions, 1 deletion)
- `src/llm_core.py`: `_build_anthropic_payload()` tool-result routing (7 insertions, 1 deletion)
- `tests/test_agent_loop.py`: updated assertion + added `TestRecentContextForRetrieval`
- `tests/test_tool_result_role.py` (new); `_build_anthropic_payload` inline routing tests

---



## Target branch

- [x] This PR targets **`dev`**, not `main`. All PRs land in `dev`; `main` is curated by the maintainer at each release.

## Linked Issue

Fixes # <!-- [file upstream issue first; see issue-drafts/fix-tool-result-role.md] -->

## Type of Change

- [x] Bug fix (non-breaking, fixes a confirmed issue)
- [ ] New feature (non-breaking, adds new behaviour)
- [ ] Breaking change (changes or removes existing behaviour)
- [ ] Refactor / cleanup (behaviour unchanged)
- [ ] Documentation only
- [ ] CI / tooling / configuration

## Filing Notes

1. **File upstream issue first**: draft in `docs/fork/upstream/issue-drafts/fix-tool-result-role.md`. Add the issue number to `Fixes #` above before opening the PR.
2. Target branch: `dev` (not `main`).
3. The PR updates the existing `test_non_native_path_unaffected` test (renamed `test_non_native_path_uses_system_role`) because the role change is the fix; the old assertion would have failed CI. Mention this proactively to show the test suite stays green.
4. The native tool path (`role=tool`) is deliberately untouched; mention this proactively to avoid reviewer confusion about why only the else-branch changed.
5. **Conflict with PR #1629 (OPEN):** "harden(agent-loop): wrap non-native tool results as untrusted data" modifies the same function (`_append_tool_results` in `src/agent_loop.py`). That PR addresses prompt injection security; this PR addresses model quality (role confusion causing hedging turns). The concerns are different but the files overlap. If #1629 merges before this PR is filed, rebase this branch against the updated upstream-mirror before opening. Mention #1629 in the PR body to show awareness and distinguish the two concerns.

## Visual / UI changes

None; no HTML, CSS, or DOM-writing JS was changed.
