"""Every memory write path constrains `category` to the allowlist.

`POST /api/memory/add` has validated it since `MemoryAddRequest` was written.
`PUT /api/memory/{id}` and the MCP `add` action did not: both took the value
raw and wrote it to storage, so an arbitrary string reached every downstream
consumer -- including `slashReply()`, which renders it into `innerHTML`.

These exercise the behaviour (call the validator / the handler body) rather than
asserting source text. A source-assertion guard here would pass on any
restructure that kept the literal while dropping the check.
"""
import pathlib

import pytest

from src.request_models import MEMORY_CATEGORIES, MemoryAddRequest, MemoryUpdateRequest

HOSTILE = '<img src=x onerror=alert(1)>'


def test_the_allowlist_is_defined_once():
    # It was previously spelled out in MemoryAddRequest.validate_category and
    # again in MemoryUpdateRequest's regex; two copies drift.
    assert set(MEMORY_CATEGORIES) == {
        "fact", "contact", "task", "preference", "identity", "project", "goal"
    }


# --- POST /api/memory/add (already correct; locked so it stays that way) -----

def test_add_coerces_a_hostile_category():
    assert MemoryAddRequest(text="x", category=HOSTILE).category == "fact"


def test_add_keeps_every_valid_category():
    for c in MEMORY_CATEGORIES:
        assert MemoryAddRequest(text="x", category=c).category == c


# --- PUT /api/memory/{id} ----------------------------------------------------
#
# Calls the REAL handler. An earlier draft of this file reimplemented the
# handler's category branch in the test, which would have passed even if the
# check were deleted from the route -- the same defect this module exists to
# close, one level up.

def _put_handler(store):
    """The real update_memory endpoint, wired to an in-memory store."""
    from unittest.mock import MagicMock
    from routes.memory.memory_routes import setup_memory_routes

    mm = MagicMock()
    mm.load_all.return_value = store
    mm.save.side_effect = lambda data: store.__setitem__(slice(None), data)
    router = setup_memory_routes(mm, MagicMock(), memory_vector=None)
    for route in router.routes:
        if getattr(route, "path", "") == "/api/memory/{memory_id}" and "PUT" in route.methods:
            return route.endpoint
    raise AssertionError("PUT /api/memory/{memory_id} not found")


def _update(category, monkeypatch=None):
    """Run the real PUT handler against a one-entry store, auth disabled."""
    from unittest.mock import MagicMock, patch
    store = [{"id": "m1", "text": "old", "category": "fact", "owner": None}]
    # get_current_user must return None (auth-disabled path); a MagicMock is
    # truthy and would fail _verify_memory_owner with a 404.
    with patch("routes.memory.memory_routes.get_current_user", return_value=None):
        _put_handler(store)(request=MagicMock(), memory_id="m1",
                            text="new", category=category)
    return store[0]["category"]


def test_update_coerces_a_hostile_category():
    assert _update(HOSTILE) == "fact"


def test_update_keeps_a_valid_category():
    assert _update("task") == "task"


def test_update_leaves_the_category_alone_when_omitted():
    # `category` is optional here; omitting it must not rewrite what is stored.
    assert _update(None) == "fact"


def test_update_model_rejects_rather_than_coerces():
    # MemoryUpdateRequest carries a regex, so it 422s where the handler coerces.
    # The divergence is deliberate and recorded: the handler matches /add's
    # coercion because rejecting would break clients already sending odd values.
    with pytest.raises(Exception):
        MemoryUpdateRequest(text="x", category=HOSTILE)
    assert MemoryUpdateRequest(text="x", category="goal").category == "goal"


# --- MCP add action ----------------------------------------------------------
#
# The MCP handler is one 400-line async dispatch function that reaches the
# network and the store, so it is exercised through its guard rather than
# called. A source assertion is the honest instrument here, and it is scoped to
# the two lines that matter rather than a whole template.

def test_mcp_add_validates_against_the_shared_allowlist():
    src = (pathlib.Path(__file__).resolve().parents[1]
           / "mcp_servers/memory_server.py").read_text(encoding="utf-8")
    add = src[src.index('elif action == "add":'):]
    add = add[:add.index("elif action ==", 10)]
    assert "MEMORY_CATEGORIES" in add, "MCP add path does not consult the allowlist"
    assert 'category = "fact"' in add, "MCP add path does not coerce"
