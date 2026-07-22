"""Regression guard: streamDocFinalize must write the textarea and code element
independently, so a missing one does not skip the final content on the survivor (#162)."""

import re
from pathlib import Path


SRC = Path(__file__).resolve().parent.parent / "static/js/document.js"


def _function_body(name: str) -> str:
    text = SRC.read_text(encoding="utf-8")
    match = re.search(rf"\n\s*(?:export\s+)?(?:async\s+)?function\s+{name}\([^)]*\)\s*\{{", text)
    assert match, f"{name} not found"

    start = match.end()
    depth = 1
    i = start
    while i < len(text) and depth:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
        i += 1
    assert depth == 0, f"{name} body did not close"
    return text[start : i - 1]


def test_finalize_writes_each_editor_element_independently():
    body = _function_body("streamDocFinalize")

    # Each element is guarded on its own — never coupled.
    assert "if (textarea) textarea.value = finalContent;" in body
    assert "if (codeEl) codeEl.textContent = finalContent + '\\n';" in body


def test_finalize_does_not_couple_the_two_elements():
    body = _function_body("streamDocFinalize")

    # The combined guard is the bug: if either element is absent, the whole
    # final-content write is skipped and the survivor keeps stale/empty text.
    assert "if (textarea && codeEl)" not in body


def test_finalize_computes_final_content_once():
    body = _function_body("streamDocFinalize")

    assert body.count("const finalContent = docs.get(oldId)?.content || '';") == 1
