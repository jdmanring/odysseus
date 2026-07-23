"""Regression guard: #welcome-screen must declare a z-index so the landing/New
Chat splash paints above #chat-history.

#chat-history carries `contain: layout style` (a stacking context) plus an
opaque `background: var(--bg)`, and sits later in the DOM than #welcome-screen.
Without an explicit z-index on the (absolutely-positioned) splash, the empty
chat log paints over and hides the whole welcome screen — branding, tip, and the
incognito button — on the landing screen. See #165."""

import re
from pathlib import Path


CSS = Path(__file__).resolve().parent.parent / "static/style.css"


def _rule_body(selector: str) -> str:
    text = CSS.read_text(encoding="utf-8")
    match = re.search(rf"(?m)^\s*{re.escape(selector)}\s*\{{", text)
    assert match, f"{selector} rule not found in style.css"
    start = match.end()
    end = text.index("}", start)
    return text[start:end]


def test_welcome_screen_declares_a_positive_zindex():
    body = _rule_body("#welcome-screen")
    m = re.search(r"z-index\s*:\s*(\d+)", body)
    assert m, (
        "#welcome-screen must declare a z-index — without it the contained, "
        "opaque #chat-history paints over the landing splash (#165)"
    )
    assert int(m.group(1)) >= 1, "#welcome-screen z-index must be >= 1 to clear #chat-history"
