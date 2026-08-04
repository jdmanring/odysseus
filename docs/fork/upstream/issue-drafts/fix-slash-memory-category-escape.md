# Upstream Issue Draft: fix-slash-memory-category-escape

> **⚠ NOT FILE-READY -- CENTRAL CLAIM FALSIFIED 2026-08-04.**
> Four independent reviewers checked this. `category` **is** validated on the
> `POST /api/memory/add` path (`src/request_models.py:42-47` coerces anything
> outside a 7-value allowlist to `fact`), so the reproduction below DOES NOT
> FIRE. The `:410` citation is the import *suggestions* payload, which never
> persists. The real unvalidated writes are `PUT /api/memory/{id}`
> (`routes/memory/memory_routes.py:512`, raw `Form`, and missing the
> `require_privilege` guard that `/add` has) and `mcp_servers/memory_server.py:161`.
> "Sole output path" is also false (`_eggRender` at `slashCommands.js:5319` is a
> second sink), and "single-user, local-first" is false (real multi-user auth;
> it is *owner-scoped*, which is the correct reason severity stays low).
> Do not file until rewritten against verified evidence.


**File on:** `odysseus-dev/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/fix-slash-memory-category-escape.md`
**Branch:** `fix/slash-memory-category-escape`
**Type:** Bug / Security (XSS)

*Line numbers are against `upstream/dev` at `fb8c391a`.*

---

## Title

`[Slash commands] Memory 'category' reaches slashReply()'s innerHTML unescaped`

---

## Body

**Area:** Frontend / slash commands

**Problem:**

`slashReply()` (`static/js/slashCommands.js:308`) assigns its argument to
`body.innerHTML`. It is the single output path for every slash command --
roughly 150 call sites across ~70 functions -- so each caller is an HTML sink.

Almost every one of them escapes correctly with `ctx.esc(...)`. Two do not, and
they are the two that render the memory store:

```js
// _cmdMemoryList
const lines = mems.slice(0, 40).map(m => `[${m.category||'fact'}] ${m.id.slice(0,8)} — ${ctx.esc(m.text)}`);

// _cmdMemorySearch
const lines = mems.map(m => `[${m.category||'fact'}] ${ctx.esc(m.text)}`);
```

`m.text` is escaped. `m.category` immediately beside it is not.

**Why `category` is not trusted input:**

It is never constrained to a fixed set on the server.

| site | value |
|---|---|
| `routes/memory/memory_routes.py:96` | `category=form.get("category", "fact")` - free-form form field |
| `routes/memory/memory_routes.py:410` | `item.get("category") or "fact"` - taken from an LLM-generated JSON array during memory import |
| `routes/memory/memory_routes.py:80` | returned to the client verbatim |

Two routes therefore influence what reaches `innerHTML`: a direct API call, and
any imported or extracted memory whose category the model writes. The second is
the one worth caring about, because it means content from an ingested document
can reach a DOM sink without the user typing anything.

**Reproduction:**

```
POST /api/memory/add   text=hello   category=<img src=x onerror=alert(1)>
```

then run `/memory` in the chat input. The payload is inserted as markup rather
than shown as text. `/memory search hello` takes the same path.

**Severity, stated honestly:**

Modest. It needs a memory entry to already carry a hostile category, and the
application is single-user and local-first, so this is not
stored-XSS-to-account-takeover. It is reported because it is an unescaped sink
directly beside an escaped one, in a file where the escaping convention is
otherwise followed, and because the import path makes it reachable without user
action.

**Note on scope:** `_cmdSessionInfo` (`static/js/slashCommands.js:1173`) has the
same shape -- three fields interpolated raw beside three escaped ones. Those
values are server-generated (uuid, timestamp, count) so no injection route was
found, but the fix is the same one line each.

`_cmdMcp` is **not** affected and should stay as it is: it builds its line
unescaped and then escapes the whole line at the join, which is the more robust
of the two patterns in this file.

**Proposed fix:**

Wrap the fields with `ctx.esc(...)`, matching every other field in the same
template, plus source-assertion guards in the style of the existing `*_js.py`
tests -- including one asserting that `slashReply` is still an `innerHTML` sink,
so the guards cannot silently end up guarding nothing.

**Related, not fixed here:** `uiModule.esc` (`static/js/ui.js:786`) is
`(s || '').replace(...)`, which throws on a number. `static/js/skills.js:19`
already works around it with `String(s ?? '')` despite the canonical helper's
docstring telling other modules to defer to it. Coercing it is a one-word change
but alters rendering for every falsy caller (`esc(0)` would render `0` rather
than an empty string), so it needs its own call-site audit rather than riding
along with a security fix.

**Willing to submit a PR:** yes, branch is ready.
