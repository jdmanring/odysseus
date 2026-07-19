"""Tests for <tool_code> Python function-call parsing (Google Gemma style).

Covers:
- bash(command=...) parsed and executed
- web_search(query=...) parsed and executed
- get_workspace() parsed and executed (zero-arg)
- MiniMax {tool => ...} path unaffected (regression)
- strip_tool_blocks removes any <tool_code> block regardless of inner format
- Unrecognised function name: stripped but not executed
- Malformed Python syntax: stripped but not executed
"""
import src.agent_tools  # noqa: F401  (break agent_tools<->tool_parsing import cycle)
from src.tool_parsing import parse_tool_blocks, strip_tool_blocks


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def test_gemma_bash_command_parsed():
    text = '<tool_code>bash(command="gh repo list --limit 10")</tool_code>'
    blocks = parse_tool_blocks(text)
    assert len(blocks) == 1
    assert blocks[0].tool_type == "bash"
    assert "gh repo list" in blocks[0].content


def test_gemma_web_search_parsed():
    text = '<tool_code>web_search(query="latest Python release")</tool_code>'
    blocks = parse_tool_blocks(text)
    assert len(blocks) == 1
    assert blocks[0].tool_type == "web_search"
    assert "Python release" in blocks[0].content


def test_gemma_tool_code_with_surrounding_text():
    text = 'Let me search for that.\n<tool_code>web_search(query="foo")</tool_code>\nDone.'
    blocks = parse_tool_blocks(text)
    assert len(blocks) == 1
    assert blocks[0].tool_type == "web_search"


def test_gemma_get_workspace_parsed():
    text = '<tool_code>get_workspace()</tool_code>'
    blocks = parse_tool_blocks(text)
    assert len(blocks) == 1
    assert blocks[0].tool_type == "get_workspace"
    assert blocks[0].content == ""


def test_gemma_unknown_function_not_executed():
    # An unrecognised function name should produce no tool block.
    text = '<tool_code>frobnicate(value="test")</tool_code>'
    blocks = parse_tool_blocks(text)
    assert blocks == []


def test_gemma_malformed_syntax_not_executed():
    text = '<tool_code>bash(command=</tool_code>'
    blocks = parse_tool_blocks(text)
    assert blocks == []


# ---------------------------------------------------------------------------
# MiniMax regression — existing {tool => ...} path must still work
# ---------------------------------------------------------------------------

def test_minimax_tool_code_still_parsed():
    text = "<tool_code>{tool => 'bash', args => '<parameter name=\"command\">ls -la</parameter>'}</tool_code>"
    blocks = parse_tool_blocks(text)
    assert len(blocks) == 1
    assert blocks[0].tool_type == "bash"


# ---------------------------------------------------------------------------
# strip_tool_blocks — _TOOL_CODE_ANY_RE strips all <tool_code> variants
# ---------------------------------------------------------------------------

def test_strip_removes_gemma_pycall_block():
    text = 'Before\n<tool_code>bash(command="ls")</tool_code>\nAfter'
    assert "tool_code" not in strip_tool_blocks(text)
    assert "Before" in strip_tool_blocks(text)
    assert "After" in strip_tool_blocks(text)


def test_strip_removes_unrecognised_tool_code_content():
    # An unrecognised format must be stripped, never shown to the user.
    text = 'Output: <tool_code>some_unknown_format()</tool_code> end'
    result = strip_tool_blocks(text)
    assert "tool_code" not in result
    assert "some_unknown_format" not in result


def test_strip_removes_minimax_tool_code_block():
    text = "<tool_code>{tool => 'bash', args => 'x'}</tool_code>"
    assert "tool_code" not in strip_tool_blocks(text)
