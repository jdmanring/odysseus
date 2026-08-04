# Upstream Issue Draft: fix-slash-memory-category-escape

**File on:** `odysseus-dev/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/fix-slash-memory-category-escape.md`
**Branch:** `fix/slash-memory-category-escape`
**Type:** Hardening (defence in depth)

*Line numbers against `upstream/dev` at `fb8c391a`.*

*Rewritten 2026-08-04. The first version reported this as an XSS with a
reproduction that does not fire, because it claimed `category` was unvalidated
server-side when `POST /api/memory/add` does validate it. The genuinely
unvalidated write paths are reported separately in
`fix-memory-category-validation.md`, which is the fix worth taking first.*

---

## Title

`[Slash commands] Four fields reach slashReply()'s innerHTML unescaped`

---

## Body

**Area:** Frontend / slash commands

**Problem:**

`slashReply()` (`static/js/slashCommands.js:308`) assigns its argument to
`body.innerHTML`. Callers that render data into it escape with `ctx.esc(...)`,
and four leave exactly one field raw next to escaped neighbours:

```js
// _cmdMemoryList / _cmdMemorySearch -- m.text escaped, m.category beside it not
const lines = mems.map(m => `[${m.category||'fact'}] ${ctx.esc(m.text)}`);

// _cmdSearch -- name and snippet escaped on the lines above; sid raw, in an attribute
return `<a href="#${sid}" ...>${name}</a>  ${snippet}`;

// _cmdSessionList -- s.name escaped, s.id not
return `${ctx.esc(s.name || 'Untitled')} <span ...>${s.id.slice(0,8)}</span>${current}`;
```

**Is it exploitable today? No, and that is worth stating up front:**

- `category` is coerced to a seven-value allowlist by `MemoryAddRequest`
  (`src/request_models.py:42-47`).
- `sid` and `s.id` are `uuid.uuid4()` (`routes/session_routes.py:426, 920`).

So this is a hardening report, not an incident. Two reasons it is still worth
taking:

1. The escaping convention in this file is per-field, so a field left out stays
   invisible until something upstream of it changes. That is not hypothetical:
   `category` was unconstrained on `PUT /api/memory/{id}` and on the MCP `add`
   path (filed separately) while these four sites were raw.
2. `_cmdSearch` is an **attribute** context, where the missing escape covers the
   double quote that ends the attribute -- a different and worse failure mode
   than the text contexts.

Memory is owner-scoped (`_verify_memory_owner` 404s on mismatch), so even with a
hostile value stored it renders only for the account that stored it. Self-XSS,
low severity.

**A related sink, not covered here:** `_eggRender` (`:5314`) is a second,
independent `innerHTML` bubble sink with 10 callers, and the hwfit probe writes
streamed response fields into `bodyEl.innerHTML` (`:5636, :5655, :5671`) with
some fields escaped and some not. Flagging rather than silently scoping out --
happy to file separately if useful.

**Proposed fix:**

Wrap the four fields with `ctx.esc(...)`, matching their neighbours, plus a
guard that fails on any `${...}` reading a property without `esc()` in the
affected functions -- so a newly added field is caught, not only the known ones.

**Willing to submit a PR:** yes, branch is ready.
