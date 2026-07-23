"""Regression guard: every code path that clears #chat-history must call
window.chatHistory.reset() BEFORE the innerHTML='' wipe (the DOM-virtualization
API contract — see static/js/chatHistory.js:12).

Skipping reset() leaves the message window's _serverTotal alive, so the header
counter (static/app.js) keeps reporting the previous session's "· N msgs" onto
the fresh screen, and the window's MutationObserver tracks a DOM it no longer
matches. #2 retrofitted six wipe sites but a repo-wide sweep found four more it
missed (#164): createDirectChat (New Chat), _cmdSessionClear (/clear), the
archived-session view, and the group-chat start handler.

The check is anchored on the exact wipe line rather than a function name so it
also covers wipes inside anonymous handlers (the group-chat one), and asserts a
reset() call appears in the source window immediately preceding the wipe."""

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
_RESET = "window.chatHistory.reset()"

# (source file, exact wipe line, human label). Each wipe line is unique within
# its file, so we anchor on it and require reset() in the preceding lines.
WIPE_SITES = [
    ("static/js/sessions.js", "if (box) box.innerHTML = '';", "createDirectChat / New Chat"),
    ("static/js/sessions.js", "if (chatBox) chatBox.innerHTML = '';", "archived-session view"),
    ("static/js/slashCommands.js", "document.getElementById('chat-history').innerHTML = '';", "/clear command"),
    ("static/js/group.js", "if (box) box.innerHTML = '';", "group-chat start"),
]

# How many source lines before the wipe the reset() may sit in (acquisition +
# a short comment + the reset itself).
_LOOKBACK = 6


def test_reset_precedes_every_chat_history_wipe():
    for rel, wipe_line, label in WIPE_SITES:
        lines = (ROOT / rel).read_text(encoding="utf-8").splitlines()

        hits = [i for i, ln in enumerate(lines) if ln.strip() == wipe_line]
        assert len(hits) == 1, (
            f"{label} ({rel}): expected exactly one `{wipe_line}` "
            f"(found {len(hits)}) — the anchor is no longer unique, update the test"
        )

        wipe_idx = hits[0]
        window = "\n".join(lines[max(0, wipe_idx - _LOOKBACK): wipe_idx])
        assert _RESET in window, (
            f"{label} ({rel}:{wipe_idx + 1}): missing `{_RESET}` in the "
            f"{_LOOKBACK} lines before the #chat-history wipe — the window layer's "
            f"observers/state must be released before the DOM is cleared (#164)"
        )
