# PR Draft: fix/slash-memory-category-escape -> odysseus-dev/odysseus:dev

**Branch:** `fix/slash-memory-category-escape`
**Issue:** #182 (fork tracking, `docs/fork/issues/INDEX.md`)
**Status:** Ready to file
**Base:** cut from `upstream-mirror`, one commit

*Fork-internal note, not PR body text: found by running the composition in
`docs/fork/post-ingest-checklist.md` step 6 - `god-nodes` ranked `slashReply`
at 69 edges, `find_referencing_symbols` showed 31 lines against ~150
references (fan-in, so worth reading), and reading it showed the sink.*

---

## Title

`fix(slash): escape memory category before it reaches the innerHTML sink`

---

## Summary

### Problem

`slashReply()` (`static/js/slashCommands.js`) assigns its argument to
`body.innerHTML`. It is the single output path for every slash command --
roughly 150 call sites across ~70 functions -- so every caller is an HTML sink.

Nearly all of them escape correctly with `ctx.esc(...)`. Two miss one field,
and they are the two that render the memory store:

```js
// _cmdMemoryList
const lines = mems.slice(0, 40).map(m => `[${m.category||'fact'}] ${m.id.slice(0,8)} — ${ctx.esc(m.text)}`);

// _cmdMemorySearch
const lines = mems.map(m => `[${m.category||'fact'}] ${ctx.esc(m.text)}`);
```

`m.text` is escaped. `m.category` immediately beside it is not.

### Why `category` is not trusted input

It is never constrained to an enum on the server:

| site | value |
|---|---|
| `routes/memory/memory_routes.py:96` | `category=form.get("category", "fact")` - free-form form field |
| `routes/memory/memory_routes.py:410` | `item.get("category") or "fact"` - from an LLM-generated JSON array on memory import |
| `routes/memory/memory_routes.py:80` | returned to the client verbatim |

So the value reaching `innerHTML` is influenced by two routes: a direct API
call, and any imported or extracted memory whose category the model writes.
The second is the one that matters, because it means document content can
reach a DOM sink without the user typing anything.

### On severity

Modest, and worth stating plainly rather than inflating. It needs a memory
entry to already carry a hostile category, and the application is single-user
and local-first, so this is not stored-XSS-to-account-takeover. It is an
unescaped sink two characters away from an escaped one, in the field next to a
field that is escaped, and the fix is the call the neighbour already makes.

## The fix

Wrap both with `ctx.esc(...)`, matching every other field in the same template.

`_cmdSessionInfo` had the same shape -- three fields interpolated raw beside
three escaped ones -- and is fixed the same way in the same commit. The numeric
ones go through `String(...)` first because `uiModule.esc` is
`(s || '').replace(...)`, which throws on a number.

`_cmdMcp` is deliberately left alone. It builds its line unescaped and then
escapes the whole line at the join, which is the more robust of the two
patterns in this file. One of the guards locks that in as the shape the
per-field sites should converge on if they are ever rewritten.

## Tests

`tests/test_slash_reply_escaping_js.py`, six source-assertion checks matching
the convention of the other `*_js.py` tests in this suite. They include a check
that `slashReply` is still an `innerHTML` sink, so if that ever changes the
suite says so rather than leaving the other five guarding nothing.

Verified by mutation: reverting either escape call fails the suite (2 tests).

Full suite on the branch: **4,795 passed, 1 skipped, 0 failed.**

## Not included

- **`uiModule.esc` does not coerce.** `(s || '').replace(...)` throws on a
  number, and the local copy in `static/js/skills.js` already uses the more
  robust `String(s ?? '')`. Changing the canonical one is a behaviour change
  for every caller (`esc(0)` would render `0` rather than an empty string), so
  it needs its own analysis and its own PR rather than riding along here.
  No live crash was found: the one call site that looked like it passed a
  number, `esc(pcount)` in `cookbook-hwfit.js`, receives `parameter_count`,
  which is a string like `"168B"`.
