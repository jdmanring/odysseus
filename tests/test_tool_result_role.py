"""Tests for _build_anthropic_payload tool-result inline routing.

When tool results are stored as role=system messages (post-fix), the Anthropic
payload builder must NOT extract them into the `system` block — that would
collapse all rounds' results into a single block before the conversation,
destroying their temporal ordering and breaking multi-round tool execution.

Instead, [Tool execution results] system messages are re-tagged as role=user
and kept inline at their position in chat_messages.  Regular system messages
(instructions, persona) continue to be extracted to the `system` block.
"""
import os
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from src.llm_core import _build_anthropic_payload

_MODEL = "claude-3-5-sonnet-20241022"


class TestToolResultInlineRouting:
    """[Tool execution results] system messages stay inline, not in system_parts."""

    def test_tool_result_goes_to_chat_messages_not_system_block(self):
        messages = [
            {"role": "user", "content": "List the files."},
            {"role": "assistant", "content": "Let me check."},
            {"role": "system", "content": "[Tool execution results]\n\nfoo.txt\nbar.txt"},
        ]
        payload = _build_anthropic_payload(_MODEL, messages, 0.7, 4096)

        chat = payload["messages"]
        inline = [m for m in chat
                  if isinstance(m.get("content"), str)
                  and m["content"].startswith("[Tool execution results]")]
        assert len(inline) == 1, "tool result must appear exactly once in chat_messages"
        assert inline[0]["role"] == "user"

    def test_tool_result_absent_from_system_block(self):
        messages = [
            {"role": "user", "content": "List the files."},
            {"role": "system", "content": "[Tool execution results]\n\nfoo.txt"},
        ]
        payload = _build_anthropic_payload(_MODEL, messages, 0.7, 4096)

        system_text = ""
        for block in payload.get("system", []):
            system_text += block.get("text", "")
        assert "[Tool execution results]" not in system_text

    def test_regular_system_message_still_extracted(self):
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello"},
        ]
        payload = _build_anthropic_payload(_MODEL, messages, 0.7, 4096)

        assert "system" in payload
        system_text = " ".join(b.get("text", "") for b in payload["system"])
        assert "helpful assistant" in system_text

    def test_tool_result_and_system_instruction_coexist(self):
        # A real agent run has both: a persona system message and tool results.
        # The instruction must go to system_parts; the tool result must stay inline.
        messages = [
            {"role": "system", "content": "You are a file manager."},
            {"role": "user", "content": "List the files."},
            {"role": "assistant", "content": "Checking now."},
            {"role": "system", "content": "[Tool execution results]\n\nfoo.txt\nbar.txt"},
        ]
        payload = _build_anthropic_payload(_MODEL, messages, 0.7, 4096)

        system_text = " ".join(b.get("text", "") for b in payload.get("system", []))
        assert "file manager" in system_text
        assert "[Tool execution results]" not in system_text

        chat = payload["messages"]
        inline = [m for m in chat
                  if isinstance(m.get("content"), str)
                  and "[Tool execution results]" in m["content"]]
        assert len(inline) == 1

    def test_multi_round_tool_results_preserve_order(self):
        # Two agent rounds each produce a tool result; they must appear in order.
        messages = [
            {"role": "user", "content": "Step 1"},
            {"role": "assistant", "content": "Round 1 response"},
            {"role": "system", "content": "[Tool execution results]\n\nresult A"},
            {"role": "user", "content": "Step 2"},
            {"role": "assistant", "content": "Round 2 response"},
            {"role": "system", "content": "[Tool execution results]\n\nresult B"},
        ]
        payload = _build_anthropic_payload(_MODEL, messages, 0.7, 4096)

        chat = payload["messages"]
        contents = [m.get("content", "") for m in chat]
        idx_a = next(i for i, c in enumerate(contents)
                     if isinstance(c, str) and "result A" in c)
        idx_b = next(i for i, c in enumerate(contents)
                     if isinstance(c, str) and "result B" in c)
        assert idx_a < idx_b, "tool results must appear in round order"

    def test_tool_result_content_preserved_exactly(self):
        content = "[Tool execution results]\n\nfoo.txt\nbar.txt\nbaz.txt"
        messages = [
            {"role": "user", "content": "List"},
            {"role": "system", "content": content},
        ]
        payload = _build_anthropic_payload(_MODEL, messages, 0.7, 4096)

        chat = payload["messages"]
        inline = next(m for m in chat
                      if isinstance(m.get("content"), str)
                      and "[Tool execution results]" in m["content"])
        assert inline["content"] == content
