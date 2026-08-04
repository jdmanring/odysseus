# PR Draft: fix/memory-category-validation -> odysseus-dev/odysseus:dev

**Branch:** `fix/memory-category-validation`
**Issue:** #184 (fork tracking); rewritten under #186
**Status:** Ready to file. Independent of `fix/slash-memory-category-escape` -- the
two touch no common file and apply in either order. Filing this one first is a
preference, not a constraint: this is the write side, that one is the render side.
**Base:** cut from `upstream-mirror`, one commit

*Line numbers against `upstream-mirror` (`fb8c391a`).*

*Rewritten 2026-08-04. The first version guarded two call sites, and two
independent reviews showed that was 2 of at least 7 write paths -- missing the
`source="ai_agent"` path its own argument rested on. It also claimed the
allowlist existed twice when it existed four times, with one copy disagreeing.*

---

## Title

`fix(memory): constrain category once, where every write path meets`

---

## Summary

`category` is validated on `POST /api/memory/add` and nowhere else.

**Validated:** `POST /api/memory/add` builds a `MemoryAddRequest`
(`routes/memory/memory_routes.py:94`), whose `validate_category` coerces
anything outside a seven-value allowlist to `fact`
(`src/request_models.py:42-47`).

**Not validated.** These reach storage with an arbitrary `category`:

| site | source | note |
|---|---|---|
| `routes/memory/memory_routes.py:512` | user | `category: str = Form(None)`, then `all_mem[i]["category"] = category` |
| `mcp_servers/memory_server.py:161` | `ai_agent` | `arguments.get("category", "fact")`, straight into `add_entry` |
| `src/ai_interaction.py:382-386` | `ai_agent` | category parsed from an LLM output line, `.lower()`, no check |
| `services/memory/memory_extractor.py:399,440` | `auto` | category straight from LLM JSON, no user action involved |
| `services/memory/memory_extractor.py:605` | `auto` | `entry["category"] = item["category"]`, direct mutation |
| `src/builtin_actions.py:240,278` | LLM | `mem["category"] = cleaned["category"]` |
| `src/memory_provider.py:143-152` | public API | `NativeMemoryProvider.remember(category=...)` |

The last four never pass a call site at all -- they mutate an entry's dict
directly -- so no per-call-site guard can reach them.

Checked and *not* defective: `routes/codex_routes.py:408` also goes through
`MemoryAddRequest`, and `memory_routes.py:410` only builds suggestions the
client re-posts to `/add`.

## The change

The check lives in `src.memory.coerce_category`, applied by
`MemoryManager.add_entry`, by `MemoryManager.save` and on load. Every write
funnels through one of those, including the direct-mutation paths.

It **coerces** to `fact` rather than rejecting, matching what `/add` has always
done, so a client already sending an odd value is not broken. It **logs** the
substitution: silently rewriting a client's field is how a client bug stays
invisible, and the previous version did it silently.

## The allowlist existed four times, and the copies disagreed

- `src/request_models.py` -- `validate_category`'s list and
  `MemoryUpdateRequest`'s regex alternation. Now one `MEMORY_CATEGORIES`.
- `src/tool_schemas.py:447` -- advertised `["fact", "event", "contact",
  "preference"]` **to the model**: it offered `event`, which is not in the
  allowlist, and omitted `task`, `identity`, `project` and `goal`. The system was
  asking the LLM for a value the server would then destroy.
- `mcp_servers/memory_server.py:115` -- the same wrong four in the MCP tool schema.
- `routes/memory/memory_routes.py:436` and
  `services/memory/memory_extractor.py:84` -- extraction prompts spelling out a
  third list, which omitted `task`.

All now derive from `MEMORY_CATEGORIES`, except `tool_schemas.py`. That one must
stay a literal, because `tests/test_tool_index_schema_parity.py`
`ast.literal_eval`s `FUNCTION_TOOL_SCHEMAS` rather than importing the module --
deliberately, to avoid pulling in heavy dependencies. Its copy is corrected and
pinned by an equality test instead, so it cannot drift.

## Scope

Validation only. Deliberately unchanged:

- **`MemoryUpdateRequest`.** It has zero non-test callers -- the `PUT` handler
  takes `Form` params -- and it has been in the tree since v1.0. Removing it is
  not this PR's business. No claim is made that its 422 and the handler's
  coercion are a designed divergence; nothing constructs it outside tests.
- **The `PUT` handler's missing `require_privilege`.** `POST /add` (`:91`) and
  `POST /import` (`:331`) take `can_manage_memory` and `PUT` does not, which
  looks like a gap until you read the neighbours: `DELETE /{id}` (`:534`) and
  `POST /{id}/pin` (`:487`) also guard with `_verify_memory_owner` alone.
  Privilege appears to gate creation while ownership gates mutating your own
  entries, so `PUT` matches its actual peers. Flagged in case that reading is
  wrong, but not changed.
- **Rejecting instead of coercing.** More correct in the abstract, breaking in
  practice, inconsistent with `/add`.
- **The escaping on the render side.** Separate PR
  (`fix/slash-memory-category-escape`).

## Tests

`tests/test_memory_category_validation.py`. They call the real `PUT` handler via
`setup_memory_routes` and drive the real MCP dispatch through `call_tool`,
asserting on what lands in storage rather than on source text.

Mutation-checked: eleven mutations each verified to fail the suite, including
the guard **inverted** rather than deleted, the guard disabled by a dead
conjunct, and the guard replaced by a **comment** still containing the literals
an earlier source-assertion test looked for.

One of those mutations found a defect in the tests themselves: the first version
asserted through `load_all()`, which coerces on read, so deleting the guard from
`save` left it passing. It now reads the stored JSON directly.

Full suite: 4815 passed, 1 skipped.
