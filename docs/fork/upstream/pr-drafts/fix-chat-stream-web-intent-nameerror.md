# PR draft: fix(routes): undefined-name NameErrors in chat_stream and hf_gguf_files

Branch: `fix/chat-stream-web-intent-nameerror` (from `upstream-mirror`, 2 commits
`3d9177e8` + `922ac960`)
Fork issues: #134, #135 (stay open until the upstream PR is filed). Base: `dev`.

## Summary

Commit `264da651` ("fix(chat): honor explicit web search denial") removed the assignment

```python
_explicit_web_intent = bool(_tool_intent and _tool_intent.category == "web")
```

together with the `and not _explicit_web_intent` denial condition it was targeting, but
three reads of the variable remain (`chat_stream` tool gating, the agent-loop kwargs, and
`stream_with_save`). Since then every `POST /api/chat_stream` raises `NameError` and chat
sending returns 500.

This PR restores the assignment only; the denial-condition removal from `264da651` stands.

A second instance of the same class, found by generalizing the guard below to every
module in `routes/`: commit `fbdec22d` ("CodeQL hardening for cookbook sync") rewrote
the exception handler in `hf_gguf_files` (`routes/cookbook_routes.py`) to log the
failure but typed `repo` for `repo_id`, so whenever the HuggingFace API request
raises, the graceful `{"ok": False, ...}` fallback path itself raises `NameError` and
`GET /api/cookbook/hf-gguf-files` returns 500. Fixed by using `repo_id`.

## Why the suite missed it

The route's policy tests are static AST/string checks on the source and never execute the
route, and `py_compile` cannot see `NameError` (a runtime error). The breakage shipped
with green tests.

## Test plan

- `tests/test_routes_defined_names.py` (new): stdlib-`symtable` guard, parametrized over
  every module in `routes/` (55 files); every name a function reads as an implicit
  global must be bound at module level, in builtins, or among the implicit module
  globals (`__file__` etc.). Catches this whole defect class with no server or model in
  the loop. Mutation-checked (detector red on a synthetic removed-assignment shape, on a
  typo-of-a-local shape, and on both pre-fix files; green on module-level, builtin,
  implicit-module-global, and closure bindings).
- Reproduced end-to-end pre-fix and verified post-fix: a real browser exchange against
  the live app (mock OpenAI-compatible backend) went from HTTP 500 to a completed
  streamed reply.

## Filing notes (fork-internal, not part of the PR body)

- Found by the first run of the long-session soak harness (the first test to execute
  the send path. The soak itself travels with the DOM-virtualization PR, not this one.
- No dependency on any other staged branch; file-able independently and early (small,
  user-facing breakage, trivial review).
