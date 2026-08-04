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
`fix-memory-category-validation.md`.*

*Revised again the same day (#187): writing the regression guard as an
executing test rather than a source scan surfaced 18 further raw fields beyond
the four originally reported, so the count in the title changed from four to 26.*

---

## Title

`[Slash commands] 26 fields reach slashReply()'s innerHTML unescaped`

---

## Body

**Area:** Frontend / slash commands

**Problem:**

`slashReply()` (`static/js/slashCommands.js:308`) assigns its argument to
`body.innerHTML`. Callers that render data into it escape with `ctx.esc(...)`.
Several leave a field raw next to escaped neighbours:

```js
// _cmdMemoryList / _cmdMemorySearch -- m.text escaped, m.category beside it not
const lines = mems.map(m => `[${m.category||'fact'}] ${ctx.esc(m.text)}`);

// _cmdSearch -- name and snippet escaped on the lines above; sid raw, in an attribute
return `<a href="#${sid}" ...>${name}</a>  ${snippet}`;

// _cmdSessionList -- s.name escaped, s.id not
return `${ctx.esc(s.name || 'Untitled')} <span ...>${s.id.slice(0,8)}</span>${current}`;
```

Those four were found by reading. Rewriting the regression guard so that it
**executes** each template with a hostile object, rather than pattern-matching
the source, then found 18 more -- almost all server-returned status and error
text rendered straight into a reply:

```js
slashReply(`Endpoint was not saved: ${data.detail || 'connection failed'}`);
slashReply(`Auto-sort skipped: ${data.reason || 'No sessions to sort'}`);
slashReply(`${config.label} sign-in failed (${result.error || 'denied'}).`);
slashReply(`Opening ${place} - ${action} (code ${start.user_code}). Waiting...`);
```

plus the `/db stats` counters, the compaction summary, and the command-help
table (`cmdDef.help`, `subDef.help`, aliases).

**Is it exploitable today? No, and that is worth stating up front:**

- `category` is coerced to a seven-value allowlist by `MemoryAddRequest`
  (`src/request_models.py:42-47`).
- `sid` and `s.id` are `uuid.uuid4()` (`routes/session_routes.py:426, 920`).
- The remainder are server-generated or come from a static provider table.

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

Wrap the fields with `ctx.esc(...)`, matching their neighbours, plus a guard
that renders each template with a hostile object and fails on any value that
reaches the output without passing through `esc()`.

A source-scanning guard is not enough here, and that is worth stating because it
was the first thing tried. A regex that treated an interpolation as safe when it
contained no `.`, or contained `esc(`, `.join(` or `.length`, passed seven live
variants -- including the original defect written as `${m['category']}`, since
bracket notation has no dot. Scoping by "template contains a tag" fails for the
same reason: the defect line has no markup, because `slashReply()` supplies the
surrounding `<pre>`.

**Willing to submit a PR:** yes, branch is ready.
