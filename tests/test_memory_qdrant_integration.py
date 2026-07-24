"""Integration tests: MemoryVectorStore and VectorRAG driven through the REAL
Qdrant adapter (qdrant-client in-memory mode), not the in-process fake.

The lane-level tests use FakeVectorStore, which can drift from the real adapter's
contract. These wire the actual consumers to a real Qdrant engine so the whole
path — encode -> upsert -> filtered query -> distance->similarity -> ranking — is
proven against the engine that ships. A deterministic hashing embedder stands in
for nomic so the tests are fast and offline: identical text yields an identical
unit vector, so an exact-text query lands at cosine distance 0 and ranks first.
"""
import hashlib

import numpy as np
import pytest


_DIM = 16


class HashEmbedder:
    """Deterministic, offline stand-in for a real embedding model. Same text ->
    same unit vector; different text -> near-orthogonal vector. Enough for
    round-trip, filtering, and exact-match ranking assertions."""

    model = "hash-test-embedder"
    url = "local://hash"

    def get_sentence_embedding_dimension(self):
        return _DIM

    def _vec(self, text: str):
        h = hashlib.sha256(text.encode("utf-8")).digest()
        v = np.frombuffer(h[:_DIM], dtype=np.uint8).astype("float32")
        v = v - v.mean()
        n = np.linalg.norm(v)
        return v / n if n else v

    def encode(self, texts, normalize_embeddings=True, is_query=False):
        return np.array([self._vec(t) for t in texts], dtype="float32")


@pytest.fixture
def real_qdrant(monkeypatch):
    """Point get_vector_client at a real in-memory Qdrant, and both embedding
    lanes at the deterministic embedder (custom lane disabled)."""
    from qdrant_client import QdrantClient
    from src.vector_client import _ClientAdapter
    import src.embedding_lanes as lanes

    adapter = _ClientAdapter(QdrantClient(location=":memory:"))
    monkeypatch.setattr("src.vector_client.get_vector_client", lambda: adapter)
    monkeypatch.setattr(lanes, "_build_local_lane_client", lambda: HashEmbedder())

    def no_custom():
        raise RuntimeError("custom lane disabled for test")

    monkeypatch.setattr(lanes, "_build_custom_client", no_custom)
    return adapter


# ── MemoryVectorStore ───────────────────────────────────────────────────────

def test_memory_store_add_search_remove_through_real_qdrant(real_qdrant, tmp_path, monkeypatch):
    monkeypatch.setenv("ODYSSEUS_DATA_DIR", str(tmp_path))
    from src.memory_vector import MemoryVectorStore

    mv = MemoryVectorStore(str(tmp_path))
    assert mv.healthy
    assert [l.dimension for l in mv._lanes] == [_DIM]

    mv.rebuild([
        {"id": "m1", "text": "a minimal init system on a rolling-release distro"},
        {"id": "m2", "text": "aria2c replaced hf_transfer for downloads"},
        {"id": "m3", "text": "dinner reservation friday at seven"},
    ])
    assert mv.count() == 3

    # exact-text query lands on its own vector first (distance 0 -> score 1)
    hits = mv.search("aria2c replaced hf_transfer for downloads", k=1)
    assert hits and hits[0]["memory_id"] == "m2"
    assert hits[0]["score"] == pytest.approx(1.0, abs=1e-3)

    mv.add("m4", "a new memory")
    assert mv.count() == 4
    mv.remove("m4")
    assert mv.count() == 3


def test_memory_store_rebuild_is_idempotent(real_qdrant, tmp_path, monkeypatch):
    monkeypatch.setenv("ODYSSEUS_DATA_DIR", str(tmp_path))
    from src.memory_vector import MemoryVectorStore

    mv = MemoryVectorStore(str(tmp_path))
    mems = [{"id": f"m{i}", "text": f"memory number {i}"} for i in range(5)]
    mv.rebuild(mems)
    mv.rebuild(mems)  # second rebuild must not duplicate
    assert mv.count() == 5


# ── VectorRAG (owner isolation + hybrid search + delete) ────────────────────

def test_vector_rag_owner_isolation_and_delete(real_qdrant, tmp_path, monkeypatch):
    monkeypatch.setenv("ODYSSEUS_DATA_DIR", str(tmp_path))
    from src.rag_vector import VectorRAG

    rag = VectorRAG(persist_directory=str(tmp_path))
    assert rag.healthy
    rag.add_document("rust ownership prevents data races", {"owner": "alice", "source": "rust.md"})
    rag.add_document("python asyncio event loop concurrency", {"owner": "alice", "source": "py.md"})
    rag.add_document("quarterly budget review in march", {"owner": "bob", "source": "budget.md"})

    # owner filter must not leak bob's doc into alice's results
    res = rag.search("rust ownership prevents data races", k=5, owner="alice")
    assert res
    assert all(r["metadata"].get("owner") == "alice" for r in res)
    assert not any(r["metadata"].get("source") == "budget.md" for r in res)

    # exact-text hybrid search ranks the matching doc first
    top = rag.search("quarterly budget review in march", k=1)
    assert top and top[0]["metadata"]["source"] == "budget.md"

    # delete-by-source removes exactly that document
    removed = rag.delete_by_source("py.md")
    assert removed == 1
    assert rag.get_stats()["document_count"] == 2
