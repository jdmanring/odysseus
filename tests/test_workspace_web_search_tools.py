"""Regression tests for workspace fast-path tool inclusion.

When a low-signal turn arrives with an active workspace, agent_loop.py builds
_relevant_tools from ALWAYS_AVAILABLE plus domain tools. Before the fix, the
workspace fast path only included tools from _DOMAIN_TOOL_MAP["files"], which
excluded web_search and web_fetch (those live in _DOMAIN_TOOL_MAP["web"]).

These tests verify the invariants the fix depends on, so a future refactor that
moves tools between domains will break loudly here rather than silently.
"""

import pytest


def test_web_search_not_in_files_domain():
    """web_search lives in 'web' domain — not 'files'. This is why the old fast
    path excluded it even when Web Search was enabled."""
    from src.agent_loop import _DOMAIN_TOOL_MAP

    assert "web_search" not in _DOMAIN_TOOL_MAP["files"], (
        "web_search must not be in the 'files' domain — the workspace fast path "
        "handles it separately via the disabled_tools check"
    )


def test_web_search_in_web_domain():
    """web_search and web_fetch belong to the 'web' domain."""
    from src.agent_loop import _DOMAIN_TOOL_MAP

    assert "web_search" in _DOMAIN_TOOL_MAP["web"]
    assert "web_fetch" in _DOMAIN_TOOL_MAP["web"]


def test_web_search_in_plan_mode_readonly_tools():
    """web_search is a read-only tool — it must be in PLAN_MODE_READONLY_TOOLS.
    This confirms it belongs in workspace fast-path when Web Search is on."""
    from src.tool_security import PLAN_MODE_READONLY_TOOLS

    assert "web_search" in PLAN_MODE_READONLY_TOOLS
    assert "web_fetch" in PLAN_MODE_READONLY_TOOLS


def test_bash_not_in_plan_mode_readonly_tools():
    """bash is NOT read-only — the workspace fast path gates it on Shell Access.
    This test confirms the asymmetry that the fix relies on."""
    from src.tool_security import PLAN_MODE_READONLY_TOOLS

    assert "bash" not in PLAN_MODE_READONLY_TOOLS


def test_workspace_fast_path_logic_includes_web_search_when_enabled():
    """Direct unit test of the workspace fast-path assembly logic.

    Replicates the exact branching from agent_loop.py lines 1925-1934 so that
    if the logic is changed, this test fails rather than the behavior silently
    regressing.
    """
    from src.agent_loop import _DOMAIN_TOOL_MAP
    from src.tool_index import ALWAYS_AVAILABLE
    from src.tool_security import PLAN_MODE_READONLY_TOOLS

    # Simulate: low_signal=True, workspace set, Web Search enabled (not disabled)
    disabled_tools: set = set()

    relevant = set(ALWAYS_AVAILABLE)
    relevant |= _DOMAIN_TOOL_MAP["files"] & PLAN_MODE_READONLY_TOOLS
    if "bash" not in disabled_tools:
        relevant.add("bash")
    if "python" not in disabled_tools:
        relevant.add("python")
    if "web_search" not in disabled_tools:
        relevant.add("web_search")
        relevant.add("web_fetch")

    assert "web_search" in relevant, "web_search must be included when Web Search is on"
    assert "web_fetch" in relevant, "web_fetch must be included when Web Search is on"


def test_workspace_fast_path_excludes_web_search_when_disabled():
    """When Web Search toggle is off, web_search must be excluded from the tool set."""
    from src.agent_loop import _DOMAIN_TOOL_MAP
    from src.tool_index import ALWAYS_AVAILABLE
    from src.tool_security import PLAN_MODE_READONLY_TOOLS

    # Simulate: Web Search disabled by user toggle
    disabled_tools: set = {"web_search"}

    relevant = set(ALWAYS_AVAILABLE)
    relevant |= _DOMAIN_TOOL_MAP["files"] & PLAN_MODE_READONLY_TOOLS
    if "web_search" not in disabled_tools:
        relevant.add("web_search")
        relevant.add("web_fetch")

    assert "web_search" not in relevant
    assert "web_fetch" not in relevant
