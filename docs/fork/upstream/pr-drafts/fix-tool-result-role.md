# PR Draft: fix/tool-result-role — SUPERSEDED

**Status:** Closed 2026-06-18. Superseded by upstream #1629 (commit `4e477741`).

---

## Why this was closed

This PR addressed two distinct problems:

**Part 1** (the core fix): change `_append_tool_results` to inject non-native tool
results as `role=system` instead of `role=user`, preventing models from treating shell
output as user intent.

**Part 2** (Anthropic compat): add a guard in `_build_anthropic_payload` to re-route
any `role=system + [Tool execution results]` messages back inline as `role=user` for
Anthropic providers, since Anthropic's API requires tool results to appear at their
temporal position in the conversation rather than being hoisted into the `system` block.

Upstream #1629 (merged 2026-06-16) implemented a stronger version of Part 1 by wrapping
tool results via `untrusted_context_message()`, which produces `role=user` with
`metadata.trusted=False`. This is strictly better than the `role=system` approach: it
applies prompt-injection hardening, keeps the message as `role=user` (compatible with
all providers without the `_build_anthropic_payload` routing guard), and uses a uniform
security envelope already applied to web content, RAG context, and email bodies.

With #1629 merged, Part 1 was redundant. Part 2 (the `_build_anthropic_payload` guard)
became dead code — the `role=system + [Tool execution results]` message format it
handled no longer exists. The guard was removed from develop in commit `eda573e1`.

The UNTRUSTED_CONTEXT_HEADER wording fix is tracked separately in
`fix/untrusted-tool-result-header` ([#48](https://github.com/jdmanring/odysseus/issues/48)).

---

## What was cleaned up on develop (commit `eda573e1`)

- `src/llm_core.py`: removed the `role=system + [Tool execution results]` dead-code guard
  from `_build_anthropic_payload`
- `tests/test_agent_loop.py`: corrected two tests that asserted the old `role=system`
  behavior; they were failing CI after #1629 merged
- `tests/test_tool_result_role.py`: deleted (tested dead code path)

## Original issue-draft

Filed in `docs/fork/upstream/issue-drafts/fix-tool-result-role.md` for reference.
Fork issue [#4](https://github.com/jdmanring/odysseus/issues/4) closed 2026-06-18.
