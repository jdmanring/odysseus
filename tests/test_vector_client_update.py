"""Regression guard for the Qdrant adapter's update() (src/vector_client.py).

The Chroma->Qdrant migration replaced the client but the _Collection adapter
shipped without an update() method, while VectorRAG.rename_owner (rag_vector.py)
calls collection.update(ids=, metadatas=) inside a bare `except Exception`. The
AttributeError was swallowed, so a username rename silently failed and orphaned
every one of that user's personal RAG documents under the old owner. See #166
(RAG owner-rename regression).

These run against a real Qdrant engine in qdrant-client's in-memory mode.
"""
import pytest


@pytest.fixture
def collection():
    from qdrant_client import QdrantClient

    from src.vector_client import _ClientAdapter

    client = _ClientAdapter(QdrantClient(location=":memory:"))
    return client.get_or_create_collection("c", metadata={"embedding_dimension": 4})


def test_update_exists():
    # The method must exist — its absence is the whole regression (swallowed
    # AttributeError in rename_owner).
    from src.vector_client import _Collection

    assert hasattr(_Collection, "update")


def test_update_rewrites_metadata_and_preserves_document(collection):
    collection.add(
        ids=["doc-1"],
        documents=["personal note"],
        metadatas=[{"owner": "alice", "source": "/n.txt"}],
        embeddings=[[1.0, 0.0, 0.0, 0.0]],
    )

    # The rename_owner call shape: rewrite the full metadata dict, new owner.
    collection.update(ids=["doc-1"], metadatas=[{"owner": "bob", "source": "/n.txt"}])

    row = collection.get(ids=["doc-1"])
    assert row["metadatas"][0]["owner"] == "bob"
    # The reserved document survives the payload merge (not passed to update).
    assert row["documents"][0] == "personal note"
    # The string id round-trips (reserved _ID_KEY untouched by set_payload).
    assert row["ids"][0] == "doc-1"


def test_update_makes_renamed_owner_reachable_by_filter(collection):
    # This is the actual failure: after rename, search filters on the new owner.
    collection.add(
        ids=["doc-1"],
        documents=["x"],
        metadatas=[{"owner": "alice"}],
        embeddings=[[0.0, 1.0, 0.0, 0.0]],
    )
    collection.update(ids=["doc-1"], metadatas=[{"owner": "bob"}])

    assert collection.get(where={"owner": "bob"})["ids"] == ["doc-1"]
    assert collection.get(where={"owner": "alice"})["ids"] == []
