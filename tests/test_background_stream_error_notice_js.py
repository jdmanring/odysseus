"""Regression guard: checkBackgroundStream must not purge the current session's
own background-stream entry before its error/completed branches run.

_purgeStaleBackgroundStreams() deletes every finished (completed/error) entry.
Called bare at the top of checkBackgroundStream it removed the current session's
'error' entry too, so the has() guard early-returned and the
"[Background stream encountered an error]" branch became dead code — a failed
background stream showed no notice. The purge must exclude the session being
handled. See #167."""

import re
from pathlib import Path


SRC = Path(__file__).resolve().parent.parent / "static/js/chat.js"


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


def test_purge_accepts_and_skips_the_excepted_session():
    text = SRC.read_text(encoding="utf-8")
    # The function takes an exceptSid parameter...
    assert re.search(r"function _purgeStaleBackgroundStreams\(\s*exceptSid\s*\)", text), \
        "_purgeStaleBackgroundStreams must accept an exceptSid parameter (#167)"
    body = _function_body("_purgeStaleBackgroundStreams")
    # ...and skips that session's entry.
    assert "sid === exceptSid" in body, \
        "_purgeStaleBackgroundStreams must skip the excepted session (#167)"


def test_checkBackgroundStream_excludes_the_current_session_from_the_purge():
    body = _function_body("checkBackgroundStream")
    assert "_purgeStaleBackgroundStreams(sessionId)" in body, \
        "checkBackgroundStream must purge with sessionId excluded, else its own " \
        "error branch is dead code (#167)"
    # The bare call is the bug.
    assert "_purgeStaleBackgroundStreams()" not in body, \
        "checkBackgroundStream must not call the purge bare (#167)"
