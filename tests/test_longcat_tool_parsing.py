"""Tests for <longcat_tool_call> parsing (Meituan LongCat style).

Covers:
- JSON format (official): {"name": "fn_name", "arguments": {"key": "val"}}
- Unknown tool name with args: passed through as raw ToolBlock (differs from
  pycall parser, which filters unknown names; longcat dispatches any name)
- Unknown tool name with no args: no ToolBlock returned
- Malformed JSON: returns [] without crashing
- Tag-pair format (non-JSON, unverified origin): not executed, always stripped
- strip_tool_blocks removes <longcat_tool_call> in all cases
- Surrounding prose does not prevent block parsing
"""
import src.agent_tools  # noqa: F401  (break agent_tools<->tool_parsing import cycle)
from src.tool_parsing import parse_tool_blocks, strip_tool_blocks


# ---------------------------------------------------------------------------
# JSON format (official — LongCat-Flash-Chat model card,
# huggingface.co/meituan-longcat/LongCat-Flash-Chat)
# ---------------------------------------------------------------------------

def test_longcat_json_bash_command_parsed():
    text = '<longcat_tool_call>{"name": "bash", "arguments": {"command": "ls -la"}}</longcat_tool_call>'
    blocks = parse_tool_blocks(text)
    assert len(blocks) == 1
    assert blocks[0].tool_type == "bash"
    assert "ls -la" in blocks[0].content


def test_longcat_json_web_search_parsed():
    text = '<longcat_tool_call>{"name": "web_search", "arguments": {"query": "Python 3.13 release"}}</longcat_tool_call>'
    blocks = parse_tool_blocks(text)
    assert len(blocks) == 1
    assert blocks[0].tool_type == "web_search"
    assert "Python 3.13" in blocks[0].content


def test_longcat_json_with_surrounding_text():
    text = 'Let me run that.\n<longcat_tool_call>{"name": "bash", "arguments": {"command": "pwd"}}</longcat_tool_call>\nDone.'
    blocks = parse_tool_blocks(text)
    assert len(blocks) == 1
    assert blocks[0].tool_type == "bash"
    assert "pwd" in blocks[0].content


def test_longcat_json_unknown_name_passes_through():
    # LongCat passes unknown names through as raw ToolBlocks (unlike pycall
    # which returns [] for unknown names). The dispatch layer handles execution.
    text = '<longcat_tool_call>{"name": "frobnicate", "arguments": {"x": "1"}}</longcat_tool_call>'
    blocks = parse_tool_blocks(text)
    assert len(blocks) == 1
    assert blocks[0].tool_type == "frobnicate"


def test_longcat_json_unknown_name_no_args_not_executed():
    text = '<longcat_tool_call>{"name": "frobnicate", "arguments": {}}</longcat_tool_call>'
    blocks = parse_tool_blocks(text)
    assert blocks == []


def test_longcat_json_malformed_does_not_crash():
    text = '<longcat_tool_call>{"name": "bash", "arguments": {</longcat_tool_call>'
    blocks = parse_tool_blocks(text)
    assert blocks == []


# ---------------------------------------------------------------------------
# Tag-pair format — stripped but not executed
# (format unverifiable; official vLLM parser uses JSON only)
# ---------------------------------------------------------------------------

def test_longcat_tagpair_not_executed():
    text = (
        '<longcat_tool_call>\n'
        'bash\n'
        '<longcat_arg_key>command</longcat_arg_key>\n'
        '<longcat_arg_value>echo hello</longcat_arg_value>\n'
        '</longcat_tool_call>'
    )
    blocks = parse_tool_blocks(text)
    assert blocks == []


def test_longcat_tagpair_unknown_name_not_executed():
    text = (
        '<longcat_tool_call>\n'
        'frobnicate\n'
        '<longcat_arg_key>x</longcat_arg_key>\n'
        '<longcat_arg_value>1</longcat_arg_value>\n'
        '</longcat_tool_call>'
    )
    blocks = parse_tool_blocks(text)
    assert blocks == []


def test_longcat_tagpair_no_name_not_executed():
    text = '<longcat_tool_call>\nfrobnicate\n</longcat_tool_call>'
    blocks = parse_tool_blocks(text)
    assert blocks == []


# ---------------------------------------------------------------------------
# strip_tool_blocks — <longcat_tool_call> must always be stripped
# ---------------------------------------------------------------------------

def test_strip_removes_longcat_json_block():
    text = 'Before\n<longcat_tool_call>{"name": "bash", "arguments": {"command": "ls"}}</longcat_tool_call>\nAfter'
    result = strip_tool_blocks(text)
    assert "longcat_tool_call" not in result
    assert "Before" in result
    assert "After" in result


def test_strip_removes_longcat_tagpair_block():
    text = (
        'Check this:\n'
        '<longcat_tool_call>\n'
        'bash\n'
        '<longcat_arg_key>command</longcat_arg_key>\n'
        '<longcat_arg_value>ls</longcat_arg_value>\n'
        '</longcat_tool_call>\n'
        'Done.'
    )
    result = strip_tool_blocks(text)
    assert "longcat_tool_call" not in result
    assert "Check this:" in result
    assert "Done." in result


def test_strip_removes_unknown_longcat_block():
    text = 'Output: <longcat_tool_call>{"name": "unknown_fn", "arguments": {}}</longcat_tool_call> end'
    result = strip_tool_blocks(text)
    assert "longcat_tool_call" not in result
    assert "unknown_fn" not in result
