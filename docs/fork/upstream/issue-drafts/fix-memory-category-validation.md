# Upstream Issue Draft: fix-memory-category-validation

**File on:** `odysseus-dev/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/fix-memory-category-validation.md`
**Branch:** `fix/memory-category-validation`
**Type:** Bug / Input validation

*Line numbers against `upstream/dev` at `fb8c391a`.*

*Rewritten 2026-08-04 under #186. The first version reported two unvalidated
write paths; there are at least seven, and the two it named were not the ones
that matter most.*

---

## Title

`[Memory] category is validated on POST /add only, and the tool schema advertises a value the server rejects`

---

## Body

**Area:** Memory / API

**Problem:**

`MemoryAddRequest.validate_category` (`src/request_models.py:42-47`) restricts
`category` to seven values and coerces anything else to `fact`. `POST
/api/memory/add` goes through it (`routes/memory/memory_routes.py:94`).

At least seven other paths write the same field with no check:

| site | source |
|---|---|
| `routes/memory/memory_routes.py:512` (`PUT /{id}`) | user |
| `mcp_servers/memory_server.py:161` | `ai_agent` |
| `src/ai_interaction.py:382-386` | `ai_agent` |
| `services/memory/memory_extractor.py:399,440` | `auto` |
| `services/memory/memory_extractor.py:605` | `auto` |
| `src/builtin_actions.py:240,278` | LLM |
| `src/memory_provider.py:143-152` | public API |

The last four assign `entry["category"] = ...` directly, so they never pass a
call site where a guard could sit.

**Why it matters beyond tidiness:**

- Most of those paths are model-written (`source="ai_agent"` or `"auto"`), so
  the value reaches storage with no user action. The usual prompt-injection
  reachability argument applies.
- `category` is rendered into the UI, including into an `innerHTML` template in
  the slash commands (being hardened separately). The point of a validated field
  is that consumers do not each have to defend against it.

**The part I would call the real bug:**

`src/tool_schemas.py:447` advertises `enum: ["fact", "event", "contact",
"preference"]` to the model. `event` is not in the server's allowlist, and
`task`, `identity`, `project` and `goal` are missing from the schema. So the
system instructs the LLM to emit a category the server does not accept, and
`mcp_servers/memory_server.py:115` carries the same wrong set. Two extraction
prompts (`routes/memory/memory_routes.py:436`,
`services/memory/memory_extractor.py:84`) spell out a third list that omits
`task`.

Four spellings of one allowlist, three of them wrong.

**Reproduction:**

```
PUT /api/memory/{id}   text=hello   category=anything-at-all
GET /api/memory        -> the entry comes back with category "anything-at-all"
```

**Proposed fix:**

One coercion at the point every write path meets (`MemoryManager.add_entry` and
`MemoryManager.save`), rather than a guard per call site, since the
direct-mutation paths have no call site. Coerce to `fact` rather than rejecting,
matching `POST /add`, and log the substitution. Derive every schema and prompt
from the one constant.

One caveat on that last part: `tests/test_tool_index_schema_parity.py`
`ast.literal_eval`s `FUNCTION_TOOL_SCHEMAS` rather than importing it, so that
one has to stay a literal. Correcting it and pinning it with an equality test
keeps the parity test's design intact.

**Deliberately not proposed:** adding `require_privilege(request,
"can_manage_memory")` to the `PUT` handler. `POST /add` (`:91`) and `POST
/import` (`:331`) take that privilege and `PUT` does not, which looks like a gap
until you read the neighbours: `DELETE /{id}` (`:534`) and `POST /{id}/pin`
(`:487`) also guard with `_verify_memory_owner` alone. Privilege appears to gate
creation while ownership gates mutating your own entries, so `PUT` is consistent
with its peers. Flagging in case that reading is wrong.

**Willing to submit a PR:** yes, branch is ready.
