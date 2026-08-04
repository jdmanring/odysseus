from pathlib import Path


def test_stream_render_helpers_are_visible_to_catch_block():
    source = Path("static/js/chat.js").read_text(encoding="utf-8")
    try_start = source.index("    try {\n      // Re-enable auto-scroll")
    catch_start = source.index("    } catch (err) {", try_start)

    outer_scope = source[:try_start]
    try_body = source[try_start:catch_start]

    assert "let _renderStream = () => {};" in outer_scope
    assert "let _cancelThinkingTimer = () => {};" in outer_scope
    assert "let _removeThinkingSpinner = () => {};" in outer_scope

    assert "_renderStream = () => {" in try_body
    assert "_cancelThinkingTimer = () => {" in try_body
    assert "_removeThinkingSpinner = () => {" in try_body
    assert "function _renderStream()" not in try_body

def test_streaming_tts_is_visible_to_catch_block():
    """streamingTTS is the fourth member of the family above and was left out.

    The catch block calls window.aiTTSManager.streamingStop() through this flag.
    Declared as a try-scoped `const` it throws ReferenceError *inside the error
    handler*, which aborts the handler at its first line -- so TTS is never
    stopped and every abort-reason message after it (timeout, offline, recovery)
    is silently dropped. The user sees an empty bubble.

    Same hoist-and-assign shape the three helpers above already use.
    """
    source = Path("static/js/chat.js").read_text(encoding="utf-8")
    try_start = source.index("    try {\n      // Re-enable auto-scroll")
    catch_start = source.index("    } catch (err) {", try_start)

    outer_scope = source[:try_start]
    try_body = source[try_start:catch_start]

    assert "let streamingTTS" in outer_scope, (
        "streamingTTS must be declared in the outer scope; a try-scoped const is "
        "unreachable from the catch block that stops streaming TTS"
    )
    assert "const streamingTTS" not in try_body
    assert "streamingTTS = !!(" in try_body
