"""Static checks for fix/google-compat-toolcalls.

Google's OpenAI-compatible endpoint sends camelCase "toolCalls" instead of
snake_case "tool_calls" in streaming deltas. Without the fallback, every
native tool call from Google's endpoint is silently dropped.

These checks verify both fallback sites in llm_core.py are present.
"""
from pathlib import Path

_SRC = (Path(__file__).resolve().parents[1] / "src" / "llm_core.py").read_text(encoding="utf-8")


def test_camelcase_toolcalls_fallback_in_delta_has_output_check():
    """The _delta_has_output guard must also check camelCase toolCalls."""
    assert '_delta0.get("toolCalls")' in _SRC


def test_camelcase_toolcalls_fallback_in_native_accumulation_loop():
    """The native tool-call accumulation loop must also check camelCase toolCalls."""
    assert 'delta.get("toolCalls")' in _SRC


def test_both_fallbacks_present():
    """Two separate get("toolCalls") calls — one in delta_has_output, one in the loop."""
    assert _SRC.count('get("toolCalls")') >= 2


def test_tool_calls_checked_before_toolCalls_in_accumulation_loop():
    """snake_case tool_calls must be tried FIRST; camelCase toolCalls is the fallback.

    Verifies the OR-chain ordering in the native accumulation loop:
        delta.get("tool_calls") or delta.get("toolCalls") or []
    If the order were reversed a snake_case provider that emits an empty list for
    tool_calls would fall through to camelCase even when snake_case is the correct key.
    """
    import re
    # Find the fallback chain line in the accumulation loop
    m = re.search(
        r'delta\.get\("tool_calls"\)\s+or\s+delta\.get\("toolCalls"\)',
        _SRC,
    )
    assert m is not None, (
        "Expected fallback chain 'delta.get(\"tool_calls\") or delta.get(\"toolCalls\")' "
        "not found in llm_core.py — check that snake_case is tried before camelCase"
    )
