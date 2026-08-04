# PR Draft: fix/slash-memory-category-escape -> odysseus-dev/odysseus:dev

**Branch:** `fix/slash-memory-category-escape`
**Issue:** #182 (fork tracking); rewritten under #187 and #188
**Status:** Ready to file. Independent of `fix/memory-category-validation` -- the two
branches touch no common file and apply in either order.
**Base:** cut from `upstream-mirror`, three commits

*Line numbers against `upstream-mirror` (`fb8c391a`).*

*Rewritten 2026-08-04. Two earlier versions were wrong in ways worth recording,
because the second was written to fix the first. The original claimed `category`
was never validated server-side and shipped a reproduction that does not fire.
The replacement guard was then defeated by seven live XSS variants on the first
attempt, including the original defect re-introduced verbatim. The commit
messages carrying the false claims were rewritten before filing; a retraction in
a side document does not un-ship a commit message.*

---

## Title

`fix(slash): escape interpolated values in slash-command output`

---

## Summary

`slashReply()` (`static/js/slashCommands.js:308`) assigns its argument to
`body.innerHTML` (`:319`). Callers build that string from template literals and
escape each field with `ctx.esc(...)`. The convention is per-field, so a field
left out is invisible until something upstream of it changes.

This PR escapes the fields that were missing it and replaces the regression
guard with one that executes.

**Fields escaped:**

| function | field | context |
|---|---|---|
| `_cmdMemoryList` | `m.category`, `m.id.slice(0,8)` | text inside `<pre>` |
| `_cmdMemorySearch` | `m.category` | text inside `<pre>` |
| `_cmdSearch` | `sid` | **`href` attribute** |
| `_cmdSessionList` | `s.id` | text |
| `_cmdSessionInfo` | `s.id`, `s.message_count`, `s.created_at` | text |

Writing the guard as an executing test then surfaced 18 more, mostly
server-returned status and error text rendered straight into `slashReply`:
`data.detail`, `data.reason`, `data.kept`, `data.updated`, `data.deleted_empty`,
`result.error`, `start.user_code`, `config.label`, `provider.name`,
`d.summarized`, `d.kept`, the `/db stats` counters, and the command-help table
(`cmdDef.help`, `subDef.help`, aliases). All escaped here.

Numeric fields are wrapped too. That is a small behaviour change -- they are
stringified through `esc` -- and it is deliberate: exempting "the numeric ones"
is how a field that stops being numeric slips through.

## Is any of it exploitable today?

No, and that is worth stating plainly. This is defence in depth, not an incident.

- `category` is coerced to a seven-value allowlist by `MemoryAddRequest` on
  `POST /api/memory/add` (`src/request_models.py:42-47`). It was **not**
  constrained on the other write paths; that is the companion PR
  (`fix/memory-category-validation`).
- `sid` and `s.id` are `uuid.uuid4()` (`routes/session_routes.py:426, 920`).
- The rest are server-generated or come from a static provider table.

Memory is owner-scoped (`_verify_memory_owner` 404s on a mismatch), so even a
stored hostile value renders only for the account that stored it. Self-XSS, low
severity.

## Deliberately unchanged

`_cmdMcp` builds its line unescaped and escapes once at the join
(`lines.map(line => ctx.esc(line)).join('\n')`, `:1561`). That is the more
robust pattern; left alone.

## A related sink, not covered here

`_eggRender` (`:5314`) is a second, independent `innerHTML` sink with 10
callers, and the hwfit probe writes streamed response fields into
`bodyEl.innerHTML` (`:5636, :5655, :5671`) with some fields escaped and some
not. Flagging rather than silently scoping out; happy to file separately.

## Tests

`tests/test_slash_reply_escaping_js.py` renders each template under node with a
hostile object and inspects the output. It does not pattern-match source.

That matters because the previous version did. It treated an interpolation as
safe if it contained no `.`, or contained the substring `esc(`, `.join(` or
`.length`. A review defeated it with seven live variants, among them
`${m['category']}` -- bracket notation has no dot, so a raw property read parsed
as a literal -- and `${fmtTag({label: m.source})}`, whose inner braces meant the
scanner found no interpolation at all. It also failed on a strictly safe
destructuring refactor, so it was wrong in both directions at once.

The executing harness: every property read yields the payload whatever syntax
reaches it; collection callbacks are applied, so the escape-at-join idiom is
recognised rather than flagged; a helper called with a hostile field returns
that field, because a wrapper is not an escape; and each template is rendered
once per candidate property forced falsy, so both branches of a ternary are
evaluated rather than only the one the defaults happen to take.

Scope is templates that reach an `innerHTML` sink, not templates containing a
tag. Filtering on markup was tried first and was wrong in the worst possible
way: the original defect is `` `[${m.category}] ${ctx.esc(m.text)}` ``, which
contains no markup because `slashReply()` supplies the surrounding `<pre>`, so
six of the seven known evasions were invisible under it. A "looks like a CSS
selector" exclusion was tried and removed for the same reason: it matched any
template starting with `[`, which silently excluded that same line.

Bare identifiers in attribute position cannot be judged at template level, since
a local's provenance is not visible there. Those get a reviewed baseline that
fails closed on anything new; it currently holds three computed values in
`_eggRender`.

Verified: all seven variants that defeated the old guard now fail the suite, and
three safe refactors (destructuring, renaming, reformatting) do not.

Escaping is detected by a marker, so the harness tests whether a field passed
through `esc` rather than what `esc` does. `ui.js` starts work at import time
and hangs under a bare node DOM shim, which is why the real escaper is not
imported.

DEFER(ui.js becomes importable under node): import the real `esc` and assert on
final rendered HTML instead of on marker presence.

Full suite: 4803 passed, 1 skipped.
