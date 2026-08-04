"""Every field interpolated into a slashReply() template must be escaped.

`slashReply()` assigns its argument to `body.innerHTML`, so it is an HTML sink
with roughly 150 call sites. The callers that render server data escape
per-field with `ctx.esc(...)`, and the defect this guards against is a single
field in that template being left out while its neighbours are escaped --
`m.category` sat unescaped next to an escaped `m.text` in both memory commands,
and memory `category` is a free-form form field that is also written by the
model on memory import.

Source-text guards, matching the convention of the other `*_js.py` tests. They
lock the escape calls in place; they do not execute the DOM.
"""
from pathlib import Path

_SRC = (Path(__file__).resolve().parents[1] / "static/js/slashCommands.js").read_text(encoding="utf-8")


def test_slash_reply_is_still_an_innerhtml_sink():
    # If this ever stops being true, the guards below are guarding nothing and
    # the whole file should be re-read rather than this test deleted.
    start = _SRC.index("function slashReply(text)")
    assert "body.innerHTML = text;" in _SRC[start:start + 600]


def test_memory_list_escapes_category_and_id():
    assert "`[${ctx.esc(m.category||'fact')}] ${ctx.esc(m.id.slice(0,8))}" in _SRC


def test_memory_search_escapes_category():
    assert "const lines = mems.map(m => `[${ctx.esc(m.category||'fact')}] ${ctx.esc(m.text)}`);" in _SRC


def test_no_unescaped_category_interpolation_remains():
    # The literal defect: category interpolated raw into a template.
    assert "${m.category||'fact'}" not in _SRC
    assert "${m.category || 'fact'}" not in _SRC


def test_session_info_escapes_every_field():
    start = _SRC.index("async function _cmdSessionInfo")
    body = _SRC[start:start + 700]
    for field in ("s.name", "s.id", "s.model", "s.folder",
                  "s.message_count", "s.created_at"):
        assert f"ctx.esc({field}" in body or f"ctx.esc(String({field}" in body, field


def test_mcp_list_escapes_the_whole_line():
    # The other escaping pattern in this file, and the more robust one: build
    # the line, escape it at the join. Kept as a guard because it is the shape
    # the per-field sites should converge on if they are ever rewritten.
    assert "lines.map(line => ctx.esc(line)).join('\\n')" in _SRC
