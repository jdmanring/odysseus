#!/usr/bin/env python3
"""Find JS identifiers a merge resolution left USED but no longer DECLARED.

Why this exists
---------------
`ruff --select F821` catches this class in Python and found two real bugs in this
merge (`auth_routes.changes`, `email_pollers._t0`): a hunk choice deleted a
declaration while auto-merged code kept using it. Valid syntax, NameError at
runtime, invisible to conflict markers and to both loss directions.

JS has the identical failure and no equivalent check here (no eslint in the venv).
`node --check` catches the DUPLICATE-declaration form loudly (it is a parse error)
but an undefined reference is a runtime error it cannot see. I had been doing this
sweep by hand, per file, five times running — which is exactly the point at which
it should stop being a habit and become a tool.

The test, per identifier:
  * declared in develop's OR upstream's version of the file
  * NOT declared anywhere in the merge result
  * but still REFERENCED in the merge result
  -> orphan: something removed the declaration and left the use behind.

Heuristic, deliberately. It reads declarations lexically rather than parsing JS, so
it can miss exotic forms and can flag a name that is legitimately global or injected.
Every hit is a CANDIDATE to read, not a verdict — same contract as the loss checks.

Usage:
    js_orphan_refs.py                 # every resolved .js in the current merge
    js_orphan_refs.py <file>...
"""
from __future__ import annotations

import re
import subprocess
import sys
import pathlib

# `const x`, `let x`, `var x`, `function x`, `class x`, and `import { x }` / `import x`
DECL = re.compile(
    r"\b(?:const|let|var|function|class)\s+([A-Za-z_$][\w$]*)"
    r"|\bimport\s+(?:\*\s+as\s+)?([A-Za-z_$][\w$]*)"
    r"|\bimport\s*\{([^}]*)\}"
    r"|\bcatch\s*\(\s*([A-Za-z_$][\w$]*)"
)
# a parameter list is a declaration site too; cheap approximation
PARAMS = re.compile(r"(?:function\s*[\w$]*\s*|\()\s*([^)]{0,300}?)\)\s*(?:=>|\{)")


def sh(*a: str) -> str:
    return subprocess.run(a, capture_output=True, text=True).stdout


# Never report these: language keywords/literals (a `= false` default was being
# parsed as a parameter NAME), and globals that are declared in no file here.
NEVER = {
    "true", "false", "null", "undefined", "this", "arguments", "async", "await",
    "return", "typeof", "new", "delete", "void", "in", "of", "instanceof",
    "window", "document", "console", "navigator", "location", "localStorage",
    "sessionStorage", "fetch", "setTimeout", "setInterval", "clearTimeout",
    "clearInterval", "requestAnimationFrame", "Promise", "Object", "Array",
    "String", "Number", "Boolean", "Math", "JSON", "Date", "Map", "Set", "Error",
    "RegExp", "URL", "Blob", "FormData", "CustomEvent", "IntersectionObserver",
}


def declared(text: str) -> set[str]:
    names: set[str] = set()
    for m in DECL.finditer(text):
        for g in m.groups():
            if not g:
                continue
            for part in g.split(","):
                part = part.strip().split(" as ")[-1].strip()
                if re.fullmatch(r"[A-Za-z_$][\w$]*", part):
                    names.add(part)
    for m in PARAMS.finditer(text):
        for part in m.group(1).split(","):
            part = part.strip().lstrip(".").split("=")[0].strip()
            if re.fullmatch(r"[A-Za-z_$][\w$]*", part):
                names.add(part)
    return names


COMMENT = re.compile(r"//[^\n]*|/\*.*?\*/", re.S)
STRING = re.compile(r"'(?:\\.|[^'\\\n])*'|\"(?:\\.|[^\"\\\n])*\"|`(?:\\.|[^`\\])*`", re.S)


def code_only(text: str) -> str:
    """Strip comments and string literals.

    Without this, every common English word in a comment ("we snapshot the
    Range", "markdown snapshots") reads as a live reference. That produced 11
    false positives and ZERO real findings on the first full sweep — precisely
    the noise level that teaches a reader to skip the tool.
    """
    return STRING.sub('""', COMMENT.sub(" ", text))


def used(text: str, name: str) -> bool:
    """A reference that is not a property access (`.name`) and not a key (`name:`)."""
    for m in re.finditer(r"(?<![.\w$])" + re.escape(name) + r"\b", text):
        tail = text[m.end():m.end() + 2]
        if tail.startswith(":"):          # object literal key
            continue
        return True
    return False


def main() -> int:
    conflicted = set(sh("git", "diff", "--name-only", "--diff-filter=U").split())
    targets = [a for a in sys.argv[1:] if not a.startswith("-")] or [
        f for f in sh("git", "diff", "--cached", "--name-only").split()
        if f.endswith(".js") and f not in conflicted
    ]

    total = 0
    for f in targets:
        p = pathlib.Path(f)
        if not p.is_file():
            continue
        cur = p.read_text(errors="replace")
        cur_code = code_only(cur)
        cur_decl = declared(cur)
        side_decl = declared(sh("git", "show", f"develop:{f}")) | \
                    declared(sh("git", "show", f"upstream-mirror:{f}"))
        # Also drop names that merely MOVED into a form this lexical scan cannot
        # see (destructuring, a for-of binding). Requiring the name to be absent
        # from the result as a whole WORD-with-declaration-keyword is too strict,
        # so additionally require it to look like an identifier someone declared:
        # skip single/double-char names and anything in NEVER.
        # `[ \t]` NOT `\s` in the binding filter below: `\s` spans newlines, so an
        # ordinary call at the start of a block body (`{\n  name(...)`) was read as a
        # destructuring binding and excluded. That silently hid a REAL orphan
        # (`_installHistoryPager`), which plain grep found instead.
        BINDING = re.compile(
            r"(?:\bfor[ \t]*\([ \t]*(?:const|let|var)[ \t]+|[,{][ \t]*)" + r"(\w+)\b")
        bound = {m.group(1) for m in BINDING.finditer(cur_code)}
        orphans = [n for n in sorted(side_decl - cur_decl)
                   if len(n) > 2 and n not in NEVER and n not in bound
                   and used(cur_code, n)]
        if orphans:
            total += len(orphans)
            print(f"\n  {f}")
            for n in orphans[:10]:
                line = next((i for i, l in enumerate(cur.splitlines(), 1)
                             if re.search(r"(?<![.\w$])" + re.escape(n) + r"\b", l)), "?")
                print(f"      {n}  (first use ~line {line}) — declared on one side, gone from the result")

    print(f"\n{'='*70}")
    print(f"scanned {len(targets)} resolved JS files, {total} candidate orphan(s)")
    print("CANDIDATES, not verdicts: a global, an injected name, or a declaration form")
    print("this lexical scan misses will show up here too. Read before acting.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
