"""Regression guards for the streaming renderer's text-only fast path (#168).

1. The fast-path guard must include `~` in its "needs re-parse" char class, or a
   `~~strikethrough~~` span streaming inside a paragraph is appended as literal
   text (markdown.js renders `~~...~~` as <del>).
2. No debug console.log / renderTail counters may ship — finalize() is called in
   production (chat.js), so the counter log fired on every finished reply."""

import re
from pathlib import Path


SRC = Path(__file__).resolve().parent.parent / "static/js/streamingRenderer.js"


def test_fast_path_guard_treats_tilde_as_markdown():
    lines = SRC.read_text(encoding="utf-8").splitlines()
    guard = [ln for ln in lines if ".test(suffix)" in ln]
    assert guard, "fast-path guard line (`.test(suffix)`) not found"
    # `~` appears only inside the guard's char class on this line.
    assert "~" in guard[0], (
        "the text-only fast-path guard must include `~` so streaming "
        "~~strikethrough~~ is re-parsed, not appended literally (#168)"
    )


def test_no_debug_instrumentation_ships():
    text = SRC.read_text(encoding="utf-8")
    assert "renderTail calls=" not in text, "debug console.log must not ship (#168)"
    assert "_rtCalls" not in text and "_rtFast" not in text, (
        "dev renderTail counters must be removed (#168)"
    )
