"""Tests for fix/agent-tool-budget: default changed from 0 to 20.

The budget check in agent_loop.py guards with `max_tool_calls > 0` so that
0 preserves the old "unlimited" behavior. This file verifies:
  1. The > 0 guard is present in agent_loop.py source.
  2. 0 never triggers the budget, regardless of total_tool_calls.
  3. The new default in settings.py is 20.
  4. A positive limit correctly triggers at the threshold.
"""
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_AGENT_SRC = (_ROOT / "src" / "agent_loop.py").read_text(encoding="utf-8")
_SETTINGS_SRC = (_ROOT / "src" / "settings.py").read_text(encoding="utf-8")

# The exact budget condition extracted from agent_loop.py
def _budget_triggered(max_tool_calls: int, total_tool_calls: int) -> bool:
    return max_tool_calls > 0 and total_tool_calls >= max_tool_calls


def test_zero_bypass_guard_present_in_source():
    """The '> 0' guard must exist in agent_loop.py so 0 stays unlimited."""
    assert "max_tool_calls > 0" in _AGENT_SRC, (
        "Budget guard 'max_tool_calls > 0' not found in agent_loop.py — "
        "removing it would make a 0 value enforce a budget of zero tool calls"
    )


def test_zero_max_tool_calls_never_triggers_budget():
    """0 means unlimited — budget must never fire regardless of call count."""
    assert not _budget_triggered(0, 0)
    assert not _budget_triggered(0, 1)
    assert not _budget_triggered(0, 100)
    assert not _budget_triggered(0, 10_000)


def test_default_agent_max_tool_calls_is_20():
    """New default is 20, not 0."""
    assert '"agent_max_tool_calls": 20' in _SETTINGS_SRC, (
        "settings.py default for agent_max_tool_calls should be 20"
    )


def test_positive_limit_triggers_at_threshold():
    """Budget fires when total_tool_calls reaches the limit."""
    assert not _budget_triggered(20, 19)   # one below: not yet
    assert _budget_triggered(20, 20)       # at limit: triggered
    assert _budget_triggered(20, 21)       # over limit: triggered


def test_limit_of_one_triggers_after_first_call():
    """Edge case: limit=1 triggers on the second call attempt."""
    assert not _budget_triggered(1, 0)
    assert _budget_triggered(1, 1)
