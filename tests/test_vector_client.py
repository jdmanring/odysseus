"""Unit tests for the Qdrant vector-store adapter (src/vector_client.py).

These exercise the Chroma-shaped contract the rest of the codebase depends on,
against a real Qdrant engine running in qdrant-client's in-memory mode (no server,
no network — CI-safe). The adapter's whole job is contract preservation, so every
Chroma behavior a caller relies on is pinned here:

  - cosine *distance* semantics (Qdrant returns a *similarity*; the adapter must
    invert it so callers' `1 - distance` stays correct, and ranking is not flipped)
  - arbitrary string IDs surviving the string->UUID->string round trip
  - `.get`/`.query` return shapes (flat vs. nested-per-query lists)
  - `where=` equality filtering
  - add/upsert/delete/count
  - collection (re)creation, dimension-mismatch recreation, and the Chroma
    "raise when the collection is absent" behavior
"""
import math

import pytest

from src.vector_client import _ClientAdapter


@pytest.fixture
def client():
    # In-memory Qdrant: the real engine, no server. Fresh per test.
    from qdrant_client import QdrantClient

    return _ClientAdapter(QdrantClient(location=":memory:"))


@pytest.fixture
def collection(client):
    return client.get_or_create_collection("c", metadata={"embedding_dimension": 4})


def _unit(*xs):
    return list(xs)


# ── distance / similarity (the inversion trap) ──────────────────────────────

def test_query_returns_cosine_distance_not_similarity(collection):
    # east/north/west unit vectors; query == east.
    collection.add(
        ids=["east", "north", "west"],
        documents=["e", "n", "w"],
        metadatas=[{}, {}, {}],
        embeddings=[_unit(1, 0, 0, 0), _unit(0, 1, 0, 0), _unit(-1, 0, 0, 0)],
    )
    r = collection.query(query_embeddings=[_unit(1, 0, 0, 0)], n_results=3, include=["distances"])
    # closest ranks first
    assert r["ids"][0][0] == "east"
    # identical -> distance ~0, orthogonal -> ~1, opposite -> ~2 (cosine DISTANCE)
    d = r["distances"][0]
    assert d[0] == pytest.approx(0.0, abs=1e-5)
    assert d[-1] == pytest.approx(2.0, abs=1e-5)
    # monotonic non-decreasing: ranking is by ascending distance
    assert d == sorted(d)


def test_ranking_not_inverted_for_near_matches(collection):
    collection.add(
        ids=["a", "b"],
        documents=["a", "b"],
        metadatas=[{}, {}],
        embeddings=[_unit(1, 0, 0, 0), _unit(0.7071, 0.7071, 0, 0)],
    )
    r = collection.query(query_embeddings=[_unit(1, 0, 0, 0)], n_results=2, include=["distances"])
    assert r["ids"][0] == ["a", "b"]
    assert r["distances"][0][0] < r["distances"][0][1]


# ── string IDs round-trip through UUID mapping ──────────────────────────────

def test_arbitrary_string_ids_roundtrip(collection):
    ids = ["mem-42", "doc/with/slashes", "hash_deadbeef", "unicode-café"]
    collection.add(
        ids=ids,
        documents=[f"d{i}" for i in range(len(ids))],
        metadatas=[{} for _ in ids],
        embeddings=[_unit(1, 0, 0, 0) for _ in ids],
    )
    got = collection.get(ids=ids)
    assert set(got["ids"]) == set(ids)
    # and via query
    r = collection.query(query_embeddings=[_unit(1, 0, 0, 0)], n_results=len(ids))
    assert set(r["ids"][0]) == set(ids)


# ── documents & metadata preserved ──────────────────────────────────────────

def test_documents_and_metadata_preserved(collection):
    collection.add(
        ids=["x"],
        documents=["the document text"],
        metadatas=[{"owner": "alice", "source": "a.md"}],
        embeddings=[_unit(1, 0, 0, 0)],
    )
    got = collection.get(ids=["x"])
    assert got["documents"] == ["the document text"]
    assert got["metadatas"] == [{"owner": "alice", "source": "a.md"}]
    # reserved payload keys are not leaked into metadata
    assert "_chroma_id" not in got["metadatas"][0]
    assert "_document" not in got["metadatas"][0]


# ── where= equality filtering ───────────────────────────────────────────────

def test_where_filter_on_query(collection):
    collection.add(
        ids=["a", "b", "c"],
        documents=["a", "b", "c"],
        metadatas=[{"owner": "x"}, {"owner": "y"}, {"owner": "x"}],
        embeddings=[_unit(1, 0, 0, 0), _unit(1, 0, 0, 0), _unit(1, 0, 0, 0)],
    )
    r = collection.query(query_embeddings=[_unit(1, 0, 0, 0)], n_results=5, where={"owner": "x"})
    assert set(r["ids"][0]) == {"a", "c"}


def test_where_filter_on_get(collection):
    collection.add(
        ids=["a", "b"],
        documents=["a", "b"],
        metadatas=[{"tool_type": "builtin"}, {"tool_type": "mcp"}],
        embeddings=[_unit(1, 0, 0, 0), _unit(0, 1, 0, 0)],
    )
    got = collection.get(where={"tool_type": "builtin"})
    assert got["ids"] == ["a"]


# ── get shapes: by id, all, include=embeddings ──────────────────────────────

def test_get_all_returns_flat_lists(collection):
    collection.add(
        ids=["a", "b"], documents=["a", "b"], metadatas=[{}, {}],
        embeddings=[_unit(1, 0, 0, 0), _unit(0, 1, 0, 0)],
    )
    got = collection.get(include=["documents", "metadatas"])
    assert set(got["ids"]) == {"a", "b"}
    assert isinstance(got["ids"], list) and isinstance(got["documents"], list)
    assert "embeddings" not in got  # not requested


def test_get_with_embeddings(collection):
    collection.add(ids=["a"], documents=["a"], metadatas=[{}], embeddings=[_unit(1, 0, 0, 0)])
    got = collection.get(ids=["a"], include=["embeddings"])
    assert len(got["embeddings"][0]) == 4
    assert got["embeddings"][0][0] == pytest.approx(1.0, abs=1e-5)


def test_query_nested_per_query_shape(collection):
    collection.add(ids=["a"], documents=["a"], metadatas=[{}], embeddings=[_unit(1, 0, 0, 0)])
    r = collection.query(
        query_embeddings=[_unit(1, 0, 0, 0)], n_results=1,
        include=["documents", "metadatas", "distances"],
    )
    # Chroma nests one list per query vector
    for key in ("ids", "distances", "documents", "metadatas"):
        assert len(r[key]) == 1 and isinstance(r[key][0], list)


# ── add / upsert / delete / count ───────────────────────────────────────────

def test_upsert_overwrites_by_id(collection):
    collection.add(ids=["a"], documents=["old"], metadatas=[{}], embeddings=[_unit(1, 0, 0, 0)])
    collection.upsert(ids=["a"], documents=["new"], metadatas=[{}], embeddings=[_unit(0, 1, 0, 0)])
    assert collection.count() == 1
    assert collection.get(ids=["a"])["documents"] == ["new"]


def test_delete(collection):
    collection.add(
        ids=["a", "b"], documents=["a", "b"], metadatas=[{}, {}],
        embeddings=[_unit(1, 0, 0, 0), _unit(0, 1, 0, 0)],
    )
    collection.delete(ids=["a"])
    assert collection.count() == 1
    assert collection.get(ids=["a"])["ids"] == []


def test_count_empty_and_populated(client):
    col = client.get_or_create_collection("k", metadata={"embedding_dimension": 4})
    assert col.count() == 0
    col.add(ids=["a"], documents=["a"], metadatas=[{}], embeddings=[_unit(1, 0, 0, 0)])
    assert col.count() == 1


# ── collection lifecycle ────────────────────────────────────────────────────

def test_get_collection_raises_when_absent(client):
    with pytest.raises(ValueError):
        client.get_collection("does-not-exist")


def test_get_or_create_is_idempotent(client):
    a = client.get_or_create_collection("c", metadata={"embedding_dimension": 4})
    a.add(ids=["x"], documents=["x"], metadatas=[{}], embeddings=[_unit(1, 0, 0, 0)])
    b = client.get_or_create_collection("c", metadata={"embedding_dimension": 4})
    assert b.count() == 1  # same collection, rows preserved


def test_dimension_mismatch_recreates_empty(client):
    a = client.get_or_create_collection("c", metadata={"embedding_dimension": 4})
    a.add(ids=["x"], documents=["x"], metadatas=[{}], embeddings=[_unit(1, 0, 0, 0)])
    assert a.count() == 1
    # Reopen at a different dimension -> dropped and recreated empty (backstop).
    b = client.get_or_create_collection("c", metadata={"embedding_dimension": 8})
    assert b.dimension == 8
    assert b.count() == 0


def test_create_requires_dimension(client):
    with pytest.raises(ValueError):
        client.get_or_create_collection("c", metadata={})


def test_delete_collection_then_get_raises(client):
    client.get_or_create_collection("c", metadata={"embedding_dimension": 4})
    client.delete_collection("c")
    with pytest.raises(ValueError):
        client.get_collection("c")
