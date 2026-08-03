"""style.css must PARSE, not merely contain the right declarations.

Every other CSS test in this suite is a source-assertion: it greps for a
declaration or asserts one is absent. None of them can see structure. A
stylesheet missing a closing brace still "contains" every rule they check, so
the whole CSS suite goes green while the file is broken from the break point to
EOF — the browser drops or mis-nests everything after it.

Measured 2026-08-02: resolving a rebase of `fix/css-render-perf` left style.css
at brace depth 1 (an appended reduced-motion block had swallowed the closing
brace of `@media (max-width: 768px)`). All 14 of that branch's own tests passed.
Only counting braces caught it.

This is deliberately crude — a real CSS parser would be better, but the failure
mode worth catching is a merge or rebase eating a brace, and depth accounting
catches that with no dependency.
"""

import re
from pathlib import Path

import pytest

CSS_PATH = Path(__file__).resolve().parent.parent / "static" / "style.css"

# Comments and quoted strings can legally contain unbalanced braces
# (`content: "}"`, a commented-out rule), so both are stripped before counting.
_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_STRING = re.compile(r"'(?:\\.|[^'\\\n])*'|\"(?:\\.|[^\"\\\n])*\"")


def _code_only(text: str) -> str:
    return _STRING.sub('""', _COMMENT.sub(" ", text))


@pytest.fixture(scope="module")
def css() -> str:
    return _code_only(CSS_PATH.read_text(encoding="utf-8"))


def test_braces_balance(css):
    opens, closes = css.count("{"), css.count("}")
    assert opens == closes, (
        f"style.css brace mismatch: {opens} '{{' vs {closes} '}}'. "
        "A merge or rebase almost certainly ate a brace; every rule after the "
        "break point is dropped or mis-nested by the browser."
    )


def test_depth_never_goes_negative(css):
    """A stray closing brace is as damaging as a missing one, and balances out
    in a plain count if the file also lost an opening brace elsewhere."""
    depth = 0
    for lineno, line in enumerate(css.splitlines(), 1):
        depth += line.count("{") - line.count("}")
        assert depth >= 0, (
            f"style.css closes more braces than it opens by line {lineno} — "
            "a stray '}' terminates its block early"
        )


def test_file_ends_at_depth_zero(css):
    """Report WHERE the imbalance starts, not just that it exists.

    The last line at depth 0 is the last point the file was structurally sound,
    which is where to look. A bare count says only 'somewhere'.
    """
    depth = 0
    last_balanced = 0
    for lineno, line in enumerate(css.splitlines(), 1):
        depth += line.count("{") - line.count("}")
        if depth == 0:
            last_balanced = lineno
    assert depth == 0, (
        f"style.css ends at brace depth {depth}; last balanced line is "
        f"{last_balanced}, so the unclosed block starts after it"
    )
