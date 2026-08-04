# PR Draft: test/css-and-path-confinement-guards -> odysseus-dev/odysseus:dev

**Branch:** `test/css-and-path-confinement-guards`
**Issue:** #176 (fork tracking, `docs/fork/issues/INDEX.md`)
**Status:** Ready to file
**Base:** cut from `upstream-mirror`, one commit (`ae942f19`), 2 files, +113

---

## Title

`test: guard style.css structure and the tool-path allowlist`

---

## Summary

Two places where the suite goes green on a file that is actually broken. Both
were found the hard way, and neither needs a production change to fix.

### 1. `style.css` can be structurally broken and pass every test

The existing CSS tests assert that declarations are **present**. They read the
stylesheet as text and match on strings, which means they cannot see brace
depth. A stylesheet whose braces do not balance still contains all the right
declarations, so every one of those assertions passes.

This is not hypothetical. Resolving a large merge left `style.css` at brace
depth 1 at end of file: an unclosed block swallowed everything after it, so
every rule past the break was silently dead in the browser. **Every existing
CSS test still passed.** The breakage was found by looking at the rendered page,
not by the suite.

The new test checks the property the others cannot:

- braces balance across the file
- depth never goes negative (a stray `}` is as broken as a missing one)
- the file ends at depth zero

It is a parser-shaped check, not a style check, so it does not constrain how
anyone writes CSS. It fails only when the file cannot be parsed as nested
blocks.

### 2. Nothing pins which roots a tool may read and write

`src/tool_execution.py` builds an allowlist of roots that file tools are
confined to. That list is a security boundary: it decides whether an agent can
read outside the data directory and the workspace.

No test pinned its contents. A change that added `$HOME` to the default roots —
which is a one-line edit, and an easy one to make while chasing a path bug —
would have failed nothing.

The new tests pin three properties:

- the default roots are what they are meant to be, and `$HOME` is not among them
- a workspace located under `$HOME` still grants access to that workspace
  (the boundary must not be so tight it breaks the normal case)
- a path escaping the allowlist raises rather than resolving

The second one matters as much as the first. A guard that only asserted "`$HOME`
is absent" would invite a fix that tightens the allowlist into uselessness; this
pins both directions.

---

## Why this is a test-only PR

Neither guard changes behaviour. The stylesheet parses today and the allowlist
is already correct today; these keep them that way. Both defects are of the kind
that a source-assertion suite structurally cannot catch, so adding more
assertions of the existing shape would not have helped.

---

## Verification

`30 passed` on an otherwise unmodified tree.

Both guards are **mutation-checked**: a guard that cannot fail is not a guard.

**CSS.** Removing the final `}` from `static/style.css` (depth 1 at EOF, the
exact shape of the real breakage):

```
tests/test_css_structural_integrity.py    2 failed, 1 passed
pytest -k css  (the existing tests)      10 passed
```

The existing suite is green on a stylesheet that cannot be parsed. That is the
entire argument for this file.

**Allowlist.** Re-adding `roots.append(os.path.expanduser("~"))` to the default
roots:

```
tests/test_tool_path_confinement.py       1 failed, 26 passed
```

Both files restored afterwards and re-run clean (3 passed / 27 passed).

---

## Scope

Two new test files, 113 lines, no production code touched.
