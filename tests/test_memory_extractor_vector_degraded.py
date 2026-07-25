"""Regression: auto memory extraction must survive a runtime vector-store
failure.

The vector index reports `.healthy` only at init time. If the embedding
backend dies later (OOM, model evicted, remote endpoint down), the per-fact
`find_similar` / `add` calls raise. Before the fix these exceptions escaped the
dedup loop, jumped past `memory_manager.save(...)`, and were swallowed by the
function's outer try/except — so EVERY validated fact from the session was
silently lost (the feature promises "Errors are logged, never raised", but it
also quietly dropped all the data).

After the fix a degraded vector store falls through to the text/fuzzy dedup
path (which the code already maintains "when vector index is unavailable") and
the facts still land in the JSON store.
"""

import asyncio
import tempfile

import src.llm_core
import src.event_bus
from src.memory import MemoryManager
from services.memory.memory_extractor import extract_and_store


class _FakeSession:
    """Minimal session: two-message history so extraction proceeds."""

    owner = "alice"
    session_id = "sess-1"

    def get_context_messages(self):
        return [
            {"role": "user", "content": "Hi, a few things about me."},
            {"role": "assistant", "content": "Noted."},
        ]


class _BrokenVectorStore:
    """Healthy at init, but every embedding-backed op raises at runtime."""

    healthy = True

    def find_similar(self, text, threshold=0.72):
        raise RuntimeError("embedding backend unavailable")

    def add(self, memory_id, text):
        raise RuntimeError("embedding backend unavailable")


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_extraction_persists_facts_when_vector_store_fails_at_runtime(monkeypatch):
    facts_json = (
        '[{"text": "Alice lives in Lisbon", "category": "fact"}, '
        '{"text": "Alice prefers tea over coffee", "category": "preference"}]'
    )

    async def _fake_llm(url, model, messages, **kwargs):
        return facts_json

    monkeypatch.setattr(src.llm_core, "llm_call_async", _fake_llm)
    # fire_event touches an async event loop / disk — neutralize it.
    monkeypatch.setattr(src.event_bus, "fire_event", lambda *a, **k: None)

    with tempfile.TemporaryDirectory() as data_dir:
        mgr = MemoryManager(data_dir)

        _run(extract_and_store(
            _FakeSession(),
            mgr,
            _BrokenVectorStore(),
            endpoint_url="http://x",
            model="m",
            headers=None,
        ))

        stored = mgr.load(owner="alice")
        texts = {e["text"] for e in stored}

    # The bug lost ALL of them (save() was never reached); both must survive.
    assert "Alice lives in Lisbon" in texts
    assert "Alice prefers tea over coffee" in texts


def test_healthy_vector_store_still_dedups_normally(monkeypatch):
    """Control: a vector hit on the user's OWN memory is honored (deduped) and
    add is not called. The vector store is a shared collection with no owner
    metadata, so a hit is only treated as a duplicate when the matched id
    resolves to this user's own (or legacy unowned) memory — otherwise the
    fact would be a cross-tenant false drop. Here the match is alice's own
    memory at ambiguous similarity (below the supersede AUTO threshold), so
    the dedup must still fire."""

    async def _fake_llm(url, model, messages, **kwargs):
        return '[{"text": "Alice lives in Lisbon", "category": "fact"}]'

    monkeypatch.setattr(src.llm_core, "llm_call_async", _fake_llm)
    monkeypatch.setattr(src.event_bus, "fire_event", lambda *a, **k: None)

    with tempfile.TemporaryDirectory() as data_dir:
        mgr = MemoryManager(data_dir)
        # Seed alice's own memory (persisted so load_all sees it) and point
        # find_similar at its real id.
        seeded = mgr.add_entry("Alice's home city is Lisbon", source="auto",
                               category="fact", owner="alice")
        mgr.save([seeded])

        class _DedupVectorStore:
            healthy = True

            def similar(self, text, k=1, floor=0.0):
                # 0.72-0.80 band: similarity alone cannot tell update from
                # duplicate, so the extractor keeps the drop behavior here.
                return [{"memory_id": seeded["id"], "similarity": 0.75}]

            def add(self, memory_id, text):  # pragma: no cover - should not run
                raise AssertionError("add should not be called for a deduped fact")

        _run(extract_and_store(
            _FakeSession(), mgr, _DedupVectorStore(),
            endpoint_url="http://x", model="m", headers=None,
        ))
        # The new fact was deduped against alice's own memory, so only the
        # seeded entry remains (no duplicate added).
        assert [e["text"] for e in mgr.load(owner="alice")] == ["Alice's home city is Lisbon"]


def test_high_similarity_own_match_supersedes_instead_of_dropping(monkeypatch):
    """>= 0.80 (the measured zero-false-positive tier): the extracted fact is
    a restatement/update of the user's own memory. It used to be DROPPED,
    which is how a stale fact outlived the conversation that corrected it.
    Now the new wording is stored and the old entry retires with history."""

    async def _fake_llm(url, model, messages, **kwargs):
        return '[{"text": "Alice lives in Lisbon", "category": "fact"}]'

    monkeypatch.setattr(src.llm_core, "llm_call_async", _fake_llm)
    monkeypatch.setattr(src.event_bus, "fire_event", lambda *a, **k: None)

    with tempfile.TemporaryDirectory() as data_dir:
        mgr = MemoryManager(data_dir)
        seeded = mgr.add_entry("Alice's home city is Lisbon", source="auto",
                               category="fact", owner="alice")
        mgr.save([seeded])

        class _RestateVectorStore:
            healthy = True
            removed = []

            def similar(self, text, k=1, floor=0.0):
                return [{"memory_id": seeded["id"], "similarity": 0.86}]

            def add(self, memory_id, text):
                pass

            def remove(self, memory_id):
                self.removed.append(memory_id)

        vec = _RestateVectorStore()
        _run(extract_and_store(
            _FakeSession(), mgr, vec,
            endpoint_url="http://x", model="m", headers=None,
        ))
        entries = {e["text"]: e for e in mgr.load(owner="alice")}
        assert "Alice lives in Lisbon" in entries          # new fact stored
        old = entries["Alice's home city is Lisbon"]        # history kept
        assert old["superseded_by"] == entries["Alice lives in Lisbon"]["id"]
        assert vec.removed == [seeded["id"]]                # stale left index
