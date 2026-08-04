"""`category` is constrained to the allowlist on every write path.

The constraint lives in one place, `src.memory.coerce_category`, and is applied
by `MemoryManager.add_entry` and `MemoryManager.save`. Every write funnels
through one or the other, including the paths that mutate an entry's dict
directly (the extractor, the cleanup action) and so never pass a call site a
guard could be attached to.

An earlier version of this module guarded two call sites instead, and two
independent reviews found it covered 2 of at least 7 write paths. The tests
below are therefore written against the chokepoint, and the ones that matter
are the ones proving a *bypassing* path is still caught.
"""
import pathlib

import pytest

from src.memory import DEFAULT_CATEGORY, MemoryManager, coerce_category
from src.request_models import MEMORY_CATEGORIES, MemoryAddRequest, MemoryUpdateRequest

HOSTILE = '<img src=x onerror=alert(1)>'


# --- the allowlist is genuinely single-source ---------------------------------

def test_no_second_copy_of_the_allowlist_in_python():
    """Fails if anyone re-spells the category list instead of importing it.

    The previous version of this test asserted the tuple's *contents*, which is
    true no matter how many copies exist -- and four existed at the time,
    including one in `tool_schemas.py` that disagreed and advertised a category
    (`event`) the server would then coerce away.
    """
    root = pathlib.Path(__file__).resolve().parents[1]
    owner = root / "src/request_models.py"
    # tool_schemas.py must keep a literal: upstream's
    # tests/test_tool_index_schema_parity.py ast.literal_eval()s
    # FUNCTION_TOOL_SCHEMAS rather than importing the module, deliberately, to
    # avoid pulling in heavy dependencies. That copy is pinned instead by
    # test_the_model_schema_matches_the_allowlist below, so it cannot drift.
    pinned = {root / "src/tool_schemas.py"}
    offenders = []
    for path in root.glob("**/*.py"):
        if "venv" in path.parts or "tests" in path.parts or path == owner:
            continue
        if path in pinned:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        # A literal list/tuple naming three or more allowlist members is a copy.
        for line in text.splitlines():
            if line.lstrip().startswith("#"):
                continue
            hits = sum(1 for c in MEMORY_CATEGORIES if f'"{c}"' in line or f"'{c}'" in line)
            if hits >= 3:
                offenders.append(f"{path.relative_to(root)}: {line.strip()[:90]}")
    assert not offenders, "allowlist re-spelled instead of imported:\n" + "\n".join(offenders)


def test_the_model_schema_matches_the_allowlist():
    """The enum handed to the LLM must be the set the server accepts.

    `tool_schemas.py` used to advertise `event` and omit four real categories,
    so the system instructed the model to emit a value it would then destroy.
    """
    import src.agent_tools  # noqa: F401  (tool_schemas is only importable via it)
    from src.tool_schemas import FUNCTION_TOOL_SCHEMAS

    for schema in FUNCTION_TOOL_SCHEMAS:
        fn = schema.get("function", {})
        if fn.get("name") == "manage_memory":
            enum = fn["parameters"]["properties"]["category"]["enum"]
            assert list(enum) == list(MEMORY_CATEGORIES)
            return
    pytest.fail("manage_memory schema not found")


# --- the chokepoint itself ----------------------------------------------------

def test_coerce_rejects_a_hostile_value():
    assert coerce_category(HOSTILE) == DEFAULT_CATEGORY


def test_coerce_keeps_every_valid_category():
    for c in MEMORY_CATEGORIES:
        assert coerce_category(c) == c


@pytest.mark.parametrize("bad", [None, "", 0, 1, [], {}, object(), "FACT", " fact "])
def test_coerce_survives_non_string_and_near_miss_input(bad):
    """Unhashable and non-string values must not raise, and near-misses must not pass."""
    assert coerce_category(bad) == DEFAULT_CATEGORY


def test_coercion_is_logged(caplog):
    """Silently rewriting a client's field is how a client bug stays invisible."""
    with caplog.at_level("WARNING", logger="src.memory"):
        coerce_category("event")
    assert any("event" in r.getMessage() for r in caplog.records), \
        "no warning logged for a coerced category"


def test_a_valid_category_is_not_logged(caplog):
    with caplog.at_level("WARNING", logger="src.memory"):
        coerce_category("task")
    assert not caplog.records, "logged a warning for a perfectly valid category"


# --- every write path, including the ones that bypass add_entry ---------------

def _manager(tmp_path):
    return MemoryManager(str(tmp_path))


def test_add_entry_coerces(tmp_path):
    entry = _manager(tmp_path).add_entry("hello", category=HOSTILE)
    assert entry["category"] == DEFAULT_CATEGORY


def _on_disk(mm):
    """Read the stored JSON directly.

    Asserting through `load_all()` would hide a regression in `save`, because
    the load path coerces too: with the `save` guard removed the value is
    written hostile to disk and cleaned up on the way back out. Mutation
    testing caught exactly that -- the first version of this test passed with
    `save`'s guard deleted.
    """
    import json
    return json.loads(pathlib.Path(mm.memory_file).read_text())


def test_save_coerces_a_direct_dict_mutation(tmp_path):
    """The extractor and the cleanup action write `entry["category"] = ...`.

    They never touch a call site, so a per-call-site guard cannot see them.
    This is the test that fails if the guard moves back out of `save`.
    """
    mm = _manager(tmp_path)
    entry = mm.add_entry("hello", category="task")
    entry["category"] = HOSTILE           # exactly what memory_extractor.py does
    mm.save([entry])
    assert _on_disk(mm)[0]["category"] == DEFAULT_CATEGORY


def test_load_coerces_values_already_in_storage(tmp_path):
    """A hostile value written before this fix must not survive a read."""
    import json
    mm = _manager(tmp_path)
    mm.save([mm.add_entry("hello")])
    raw = json.loads(pathlib.Path(mm.memory_file).read_text())
    raw[0]["category"] = HOSTILE
    pathlib.Path(mm.memory_file).write_text(json.dumps(raw))
    assert mm.load_all()[0]["category"] == DEFAULT_CATEGORY


def test_save_preserves_a_valid_category(tmp_path):
    mm = _manager(tmp_path)
    entry = mm.add_entry("hello", category="project")
    mm.save([entry])
    assert mm.load_all()[0]["category"] == "project"


# --- POST /api/memory/add (already correct; locked so it stays that way) -----

def test_add_request_coerces_a_hostile_category():
    assert MemoryAddRequest(text="x", category=HOSTILE).category == DEFAULT_CATEGORY


def test_add_request_keeps_every_valid_category():
    for c in MEMORY_CATEGORIES:
        assert MemoryAddRequest(text="x", category=c).category == c


def test_update_model_still_rejects():
    """`MemoryUpdateRequest` is upstream's and unused by the PUT handler.

    Pinned only so the shared pattern keeps compiling against the constant. No
    claim is made that its 422 and the handler's coercion are a designed
    divergence: nothing constructs this model outside tests.
    """
    with pytest.raises(Exception):
        MemoryUpdateRequest(text="x", category=HOSTILE)
    assert MemoryUpdateRequest(text="x", category="goal").category == "goal"


# --- PUT /api/memory/{id}, through the real handler ---------------------------

def _put_handler(store):
    """The real update_memory endpoint, wired to an in-memory store."""
    from unittest.mock import MagicMock
    from routes.memory.memory_routes import setup_memory_routes

    mm = MagicMock()
    mm.load_all.return_value = store
    # save() must apply the real coercion; that is the behaviour under test.
    mm.save.side_effect = lambda data: store.__setitem__(
        slice(None), [dict(e, category=coerce_category(e.get("category"))) for e in data]
    )
    router = setup_memory_routes(mm, MagicMock(), memory_vector=None)
    for route in router.routes:
        if getattr(route, "path", "") == "/api/memory/{memory_id}" and "PUT" in route.methods:
            return route.endpoint
    raise AssertionError("PUT /api/memory/{memory_id} not found")


def _update(category, seeded="task"):
    """Run the real PUT handler against a one-entry store, auth disabled."""
    from unittest.mock import MagicMock, patch
    # Seeded with a NON-default category on purpose: seeded with "fact", the
    # omitted-category test below asserts "fact" == "fact" and passes even if
    # the `if category:` guard is deleted -- which would silently rewrite every
    # user's category to "fact" on any text-only edit.
    store = [{"id": "m1", "text": "old", "category": seeded, "owner": None}]
    with patch("routes.memory.memory_routes.get_current_user", return_value=None):
        _put_handler(store)(request=MagicMock(), memory_id="m1",
                            text="new", category=category)
    return store[0]["category"]


def test_update_coerces_a_hostile_category():
    assert _update(HOSTILE) == DEFAULT_CATEGORY


def test_update_keeps_a_valid_category():
    assert _update("goal") == "goal"


def test_update_leaves_the_category_alone_when_omitted():
    assert _update(None, seeded="task") == "task"


# --- MCP add action -----------------------------------------------------------

def test_mcp_add_reaches_the_chokepoint(tmp_path, monkeypatch):
    """Drive the real MCP dispatch and assert on what lands in storage.

    The previous version asserted two literals were present in the source of
    the add branch. A review passed it with the guard inverted, with the guard
    disabled by `and False`, and with the guard replaced by a comment
    containing the literals.
    """
    import asyncio
    import mcp_servers.memory_server as ms

    mm = MemoryManager(str(tmp_path))
    monkeypatch.setattr(ms, "_memory_manager", mm, raising=False)
    monkeypatch.setattr(ms, "_memory_vector", None, raising=False)
    monkeypatch.setattr(ms, "_ensure_init", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(ms, "_scope_entries", lambda: (None, mm.load_all(), None, None),
                        raising=False)

    asyncio.run(ms.call_tool("manage_memory",
                             {"action": "add", "text": "hi", "category": HOSTILE}))

    stored = mm.load_all()
    assert stored, "MCP add wrote nothing; the harness no longer drives the real path"
    assert stored[-1]["category"] == DEFAULT_CATEGORY
