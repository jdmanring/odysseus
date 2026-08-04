# PR Draft: fix/memory-category-validation -> odysseus-dev/odysseus:dev

**Branch:** `fix/memory-category-validation`
**Issue:** #184 (fork tracking)
**Status:** Ready to file. **File this before `fix/slash-memory-category-escape`** -- this is the root cause; that one hardens the output side.
**Base:** cut from `upstream-mirror`, one commit

*Line numbers against `upstream-mirror` (`fb8c391a`). Every one re-verified
against that ref before writing.*

---

## Title

`fix(memory): constrain category on the update and MCP write paths`

---

## Summary

`category` is validated on one of the three memory write paths.

**Validated:** `POST /api/memory/add` builds a `MemoryAddRequest`
(`routes/memory/memory_routes.py:94`), whose `validate_category` coerces
anything outside a seven-value allowlist to `fact`
(`src/request_models.py:42-47`).

**Not validated:**

| site | code |
|---|---|
| `routes/memory/memory_routes.py:512` | `category: str = Form(None)`, then `all_mem[i]["category"] = category` at `:521` |
| `mcp_servers/memory_server.py:161` | `arguments.get("category", "fact")`, straight into `add_entry` |

So the store accepts values on two paths that the third rejects, and every
consumer downstream inherits them. The MCP one is the one I would weight: it is
the `source="ai_agent"` path, so the value is model-written and reaches storage
with no user action.

`MemoryUpdateRequest` (`src/request_models.py:52`) already carries the correct
allowlist as a regex and is simply not used by the `PUT` handler.

## The change

Both paths now apply the same allowlist. They **coerce** to `fact` rather than
rejecting, matching `POST /add`, so a client already sending an odd value is not
broken by the upgrade. `MemoryUpdateRequest`'s regex would reject (422); that
divergence is deliberate and pinned by a test rather than left as a surprise.

The allowlist itself was written out twice -- once in `validate_category`, once
in `MemoryUpdateRequest`'s pattern -- so it is now `MEMORY_CATEGORIES`, defined
once and consumed by both. Two copies of a security-relevant list can drift, and
these were already spelled differently (list vs regex alternation).

## Scope

Validation only. Three things I looked at and deliberately did not change:

- **The `PUT` handler's missing `require_privilege`.** `POST /add` (`:91`) and
  `POST /import` (`:331`) take `can_manage_memory`; `PUT` does not. I was going
  to add it, then read the rest of the router: `DELETE /{id}` (`:534`) and
  `POST /{id}/pin` (`:487`) also guard with `_verify_memory_owner` alone. The
  pattern is coherent -- privilege gates creation, ownership gates mutating your
  own entries -- so `PUT` is consistent with its actual peers and adding the
  guard would break that, not restore it.
- **Rejecting instead of coercing.** More correct in the abstract, breaking in
  practice, and inconsistent with `/add`.
- **The escaping on the render side.** Separate PR
  (`fix/slash-memory-category-escape`), which is defence in depth for the same
  field.

## Tests

`tests/test_memory_category_validation.py`, 8 tests, calling the real `PUT`
handler via `setup_memory_routes` rather than reimplementing its logic. The
first draft of the test file did reimplement the category branch, which would
have passed with the guard deleted from the route -- the same defect this PR
closes, one level up. Mutation-checked: removing either guard fails the suite.

The MCP `add` action is one long async dispatch that reaches the network and the
store, so its guard is asserted on source, scoped to that action's block rather
than the file.
