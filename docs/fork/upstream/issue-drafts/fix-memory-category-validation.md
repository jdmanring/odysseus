# Upstream Issue Draft: fix-memory-category-validation

**File on:** `odysseus-dev/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/fix-memory-category-validation.md`
**Branch:** `fix/memory-category-validation`
**Type:** Bug / Input validation

*Line numbers against `upstream/dev` at `fb8c391a`.*

---

## Title

`[Memory] category is validated on POST /add but not on PUT /{id} or the MCP add path`

---

## Body

**Area:** Memory / API

**Problem:**

`MemoryAddRequest.validate_category` (`src/request_models.py:42-47`) restricts
`category` to seven values and coerces anything else to `fact`. `POST
/api/memory/add` goes through it (`routes/memory/memory_routes.py:94`).

Two other paths write the same field without that check:

```python
# routes/memory/memory_routes.py:512
def update_memory(request, memory_id, text: str = Form(...), category: str = Form(None)):
    ...
    if category:
        all_mem[i]["category"] = category          # :521, verbatim

# mcp_servers/memory_server.py:161
category = arguments.get("category", "fact")
entry = _memory_manager.add_entry(text, source="ai_agent", category=category, owner=owner)
```

So the store holds values that one third of the write surface would have
rejected, and every consumer downstream inherits them.

**Reproduction:**

```
PUT /api/memory/{id}   text=hello   category=anything-at-all
GET /api/memory        -> the entry comes back with category "anything-at-all"
```

**Why it matters beyond tidiness:**

- The MCP path is `source="ai_agent"`. The value is written by the model, so it
  reaches storage with no user action -- the usual prompt-injection reachability
  argument applies.
- `category` is rendered into the UI. In the slash-command output it lands in an
  `innerHTML` template (`static/js/slashCommands.js`), which is being hardened
  separately, but the point of a validated field is that consumers do not each
  have to defend against it.
- `MemoryUpdateRequest` (`src/request_models.py:52`) **already declares the
  correct allowlist** as a regex and the `PUT` handler simply does not use it.
  The intent is in the codebase; only the wiring is missing.

**Note on the allowlist itself:** it exists twice, as a Python list in
`validate_category` and as a regex alternation in `MemoryUpdateRequest`. They
agree today. Two copies of a security-relevant list can drift, so the PR
collapses them to one constant.

**Proposed fix:**

Apply the same allowlist on both paths. Coerce to `fact` rather than rejecting,
matching `POST /add`, so existing clients sending odd values are not broken.

**Deliberately not proposed:** adding `require_privilege(request,
"can_manage_memory")` to the `PUT` handler. `POST /add` (`:91`) and `POST
/import` (`:331`) take that privilege and `PUT` does not, which looks like a
gap until you read the neighbours: `DELETE /{id}` (`:534`) and `POST /{id}/pin`
(`:487`) also guard with `_verify_memory_owner` alone. The privilege appears to
gate creation while ownership gates mutating your own entries, so `PUT` is
consistent with its peers. Flagging it in case that reading is wrong, but not
changing it.

**Willing to submit a PR:** yes, branch is ready.
