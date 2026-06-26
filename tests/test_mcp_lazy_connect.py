"""Lazy-connect for cold built-in MCP servers (issue #111).

image_gen / rag / email are registered as *deferred* at startup (no subprocess
spawned, ~50 MB saved each) and connected on their first tool call. `memory`
stays eager. Built-in tool descriptions are static in the agent prompt, so a
deferred connection never hides the tools from the model.

Pattern reference: mcp-gateway / lazy-mcp — see docs/fork/mcp-lazy-connect-research.md.
"""
import asyncio
from pathlib import Path

from src.mcp_manager import McpManager as MCPManager


def test_mark_deferred_sets_status():
    m = MCPManager()
    m.mark_deferred("email", "Built-in: Email")
    assert m._is_deferred("email")
    assert m.get_server_status("email")["status"] == "deferred"
    assert m.get_server_status("email")["name"] == "Built-in: Email"


def test_mark_deferred_is_noop_when_connected():
    m = MCPManager()
    m._connections["email"] = {"status": "connected", "name": "Built-in: Email"}
    m.mark_deferred("email", "Built-in: Email")
    # Must not downgrade a live connection to deferred.
    assert m.get_server_status("email")["status"] == "connected"
    assert not m._is_deferred("email")


def test_lazy_connect_spawns_on_first_call():
    m = MCPManager()
    m.mark_deferred("email", "Built-in: Email")
    calls = {"reconnect": 0, "do_call": 0}

    async def fake_reconnect(server_id):
        calls["reconnect"] += 1
        m._sessions[server_id] = object()  # simulate spawned session
        m._connections[server_id] = {"status": "connected", "name": "Built-in: Email"}
        return True

    async def fake_do_call(session, tool_name, arguments):
        calls["do_call"] += 1
        return {"output": "ok", "exit_code": 0}

    m._reconnect_builtin = fake_reconnect
    m._do_call = fake_do_call

    result = asyncio.run(m.call_tool("mcp__email__send_email", {"to": "x"}))
    assert calls["reconnect"] == 1   # spawned exactly once, on first use
    assert calls["do_call"] == 1
    assert result["exit_code"] == 0
    assert not m._is_deferred("email")  # now connected; future calls reuse it


def test_no_lazy_connect_when_already_connected():
    m = MCPManager()
    m._sessions["memory"] = object()
    m._connections["memory"] = {"status": "connected", "name": "Built-in: Memory"}
    calls = {"reconnect": 0}

    async def fake_reconnect(server_id):
        calls["reconnect"] += 1
        return True

    async def fake_do_call(session, tool_name, arguments):
        return {"output": "ok", "exit_code": 0}

    m._reconnect_builtin = fake_reconnect
    m._do_call = fake_do_call

    asyncio.run(m.call_tool("mcp__memory__manage_memory", {}))
    assert calls["reconnect"] == 0  # already connected: no spawn


# --- static guards on the registration policy ---------------------------------

_BUILTIN_SRC = Path("src/builtin_mcp.py").read_text(encoding="utf-8")


def test_only_memory_is_eager():
    from src.builtin_mcp import _EAGER_SERVERS
    assert _EAGER_SERVERS == {"memory"}


def test_registration_branches_eager_vs_deferred():
    assert "if server_id in _EAGER_SERVERS:" in _BUILTIN_SRC
    assert "mcp_manager.mark_deferred(server_id, name)" in _BUILTIN_SRC
