# PR Draft: fix/slash-memory-category-escape -> odysseus-dev/odysseus:dev

**Branch:** `fix/slash-memory-category-escape`
**Issue:** #182 (fork tracking)
**Status:** Ready to file. **File `fix/memory-category-validation` (#184) first** -- that is the root cause; this is the output-side half.
**Base:** cut from `upstream-mirror`, two commits

*Rewritten 2026-08-04. The first version claimed `category` was never validated
server-side and shipped a reproduction that does not fire; four independent
reviews falsified it. Everything below was re-verified line by line against
`upstream-mirror` (`fb8c391a`). Nothing between the `---` markers is
fork-internal -- the tooling note that used to sit here has been removed.*

---

## Title

`fix(slash): escape interpolated values in slash-command output`

---

## Summary

`slashReply()` (`static/js/slashCommands.js:308`) assigns its argument to
`body.innerHTML`. Most callers that build HTML escape their fields with
`ctx.esc(...)`. Four did not, each leaving one field raw beside escaped
neighbours:

| function | field | context |
|---|---|---|
| `_cmdMemoryList` | `m.category` | text inside `<pre>` |
| `_cmdMemorySearch` | `m.category` | text inside `<pre>` |
| `_cmdSearch` | `sid` | **`href` attribute** |
| `_cmdSessionList` | `s.id` | text |

`_cmdSessionInfo` interpolated three server-generated fields raw as well, and is
fixed the same way.

This is defence in depth, not an exploit report. None of the four is reachable
with a hostile value on a stock `dev` today:

- `category` is coerced to a seven-value allowlist by `MemoryAddRequest`
  (`src/request_models.py:42-47`) on `POST /api/memory/add`. It was **not**
  constrained on `PUT /api/memory/{id}` or on the MCP `add` action; that is the
  companion PR (`fix/memory-category-validation`) and it is the real fix.
- `sid` and `s.id` are `uuid.uuid4()` server-side.

So: these are the fields that would carry an injection if any upstream path
stopped constraining them, and one of those paths was in fact unconstrained
until the companion PR. Memory is owner-scoped (`_verify_memory_owner`), so even
then the payload renders only for the account that stored it -- self-XSS, low
severity.

## Deliberately unchanged

`_cmdMcp` builds its line unescaped and escapes once at the join
(`lines.map(line => ctx.esc(line))`). That is correct; left alone.

## Tests

`tests/test_slash_reply_escaping_js.py` -- computed-property checks rather than
string comparisons. They parse each guarded function body and fail on any
`${...}` that reads a property without `esc()`, so a **newly added** unescaped
field fails too. An enumerated list of known field names cannot do that.

The first version asserted four exact source literals were present. A review
built a variant with three live XSS holes that passed all six of them -- the
literals survived inside a function nothing called -- while three harmless
reformats broke the suite. They tested the formatter. After the rewrite,
verified: adding an unescaped field fails, the dead-code variant fails, `||`
spacing does not.

Known ceiling: these read source rather than executing it, because `ui.js`
raises `ReferenceError: HTMLInputElement is not defined` on a bare `node`
import. 39 of this repo's 49 `*_js.py` tests do execute under `node`, and that
is the better instrument -- feed a breakout payload through the template and
assert on rendered output, as `tests/test_calendar_css_url_escape_js.py` does.
Happy to do it that way if you would rather have the harness change first.
