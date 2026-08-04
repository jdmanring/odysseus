"""Every property interpolated into slash-command HTML must go through esc().

`slashReply()` assigns its argument to `body.innerHTML`, so any `${...}` reaching
it is an HTML sink. The defect this guards against is one field being left raw
while its neighbours are escaped: `m.category` sat unescaped beside an escaped
`m.text` in both memory commands, and `sid` sat unescaped in an `href` attribute
beside an escaped `name`.

These are COMPUTED-PROPERTY checks, not string comparisons. The first version of
this file asserted that four exact source literals were present, which was worse
than useless in both directions: an audit built a variant with three live XSS
holes that passed all six assertions (the literals survived inside a function
nothing called), while three harmless reformats -- spaces around `||`, `m =>` to
`(m) =>` -- broke it. A guard that passes when vulnerable and fails when
reformatted is testing the formatter.

Parsing JS with a regex is a known ceiling; it holds because it reads a single
brace-matched function body at a time rather than the whole file.
DEFER(ui.js becomes importable under node without a DOM): replace with a
node-executed test that feeds a breakout payload through the real template and
asserts on rendered output, matching tests/test_calendar_css_url_escape_js.py.
"""
import re
from pathlib import Path

_SRC = (Path(__file__).resolve().parents[1] / "static/js/slashCommands.js").read_text(encoding="utf-8")

# `${ ... }` holes containing a property read (a dot that is not a method call).
_HOLE = re.compile(r"\$\{([^{}]*)\}")
# Values that are not attacker-influenced text: literals, arithmetic on lengths,
# and the two whole-line escape idioms this file uses.
_SAFE = re.compile(
    r"""^(?:
          [^.]*                      # no property read at all
        | .*\.length\b.*             # counts
        | .*\.join\(.*               # a joined list, escaped per element above
        | .*\bctx\.esc\(.*           # already escaped
        | .*\besc\(.*
    )$""",
    re.X | re.S,
)


def _body(name: str) -> str:
    """Brace-matched body of a top-level `function name(` / `async function name(`."""
    m = re.search(rf"^(?:async )?function {re.escape(name)}\(", _SRC, re.M)
    assert m, f"{name} not found"
    i = _SRC.index("{", m.start())
    depth = 0
    for j in range(i, len(_SRC)):
        if _SRC[j] == "{":
            depth += 1
        elif _SRC[j] == "}":
            depth -= 1
            if depth == 0:
                return _SRC[m.start():j + 1]
    raise AssertionError(f"unbalanced braces in {name}")


def _raw_property_holes(fn: str) -> list[str]:
    """Interpolations in `fn` that read a property without escaping it."""
    return [h.strip() for h in _HOLE.findall(_body(fn))
            if "." in h and not _SAFE.match(h.strip())]


# The functions that build HTML handed to slashReply(). Each was a real defect
# site or sits directly beside one.
GUARDED = [
    "_cmdMemoryList",
    "_cmdMemorySearch",
    "_cmdSessionInfo",
    "_cmdSessionList",
    "_cmdSearch",
]


def test_slash_reply_is_still_an_innerhtml_sink():
    # If this stops being true the rest of the file is guarding nothing, so it
    # must fail loudly rather than keep passing for the wrong reason.
    start = _SRC.index("function slashReply(text)")
    assert "body.innerHTML = text;" in _SRC[start:start + 600]


def test_no_guarded_function_interpolates_a_raw_property():
    # Catches a NEW unescaped field, which an enumerated list of known field
    # names structurally cannot.
    offenders = {fn: raw for fn in GUARDED if (raw := _raw_property_holes(fn))}
    assert not offenders, f"unescaped property interpolations: {offenders}"


def test_the_check_can_actually_fail():
    # Guards the guard: if _SAFE ever widens to match everything, the test above
    # passes vacuously and silently. This proves the detector still detects.
    assert _raw_property_holes.__doc__  # sanity
    hole = _HOLE.findall("`[${m.category}] ${ctx.esc(m.text)}`")
    assert "m.category" in hole and not _SAFE.match("m.category")
    assert _SAFE.match("ctx.esc(m.text)")


def test_memory_category_specifically_is_escaped():
    # The original defect, named explicitly so a regression is legible.
    for fn in ("_cmdMemoryList", "_cmdMemorySearch"):
        assert "ctx.esc(m.category" in _body(fn), fn


def test_search_result_id_is_escaped_in_the_href_attribute():
    # Attribute context: esc() escapes the double quote, so this is the fix.
    assert 'href="#${ctx.esc(sid)}"' in _body("_cmdSearch")


def test_mcp_list_escapes_at_the_join():
    # The other escaping idiom in this file, and the more robust one: build the
    # line, escape it once at the join. Kept because _SAFE treats `.join(` as
    # safe, which is only true while this holds.
    assert "lines.map(line => ctx.esc(line)).join('\\n')" in _body("_cmdMcp")
