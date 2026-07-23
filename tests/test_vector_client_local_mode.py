"""get_vector_client() backend-mode selection (src/vector_client.py).

Modes: QDRANT_HOST -> external server; QDRANT_EMBEDDED -> the single-writer
embedded on-disk store; default -> an app-managed local Qdrant server (with the
embedded store as the fallback where no server binary exists, e.g. OpenBSD).

Guards:
  * QDRANT_EMBEDDED resolves a working client with NO server, on disk, and
  * QDRANT_HOST set + unreachable RAISES rather than silently degrading.
"""
import pytest


def test_embedded_mode_works_without_a_server(monkeypatch, tmp_path):
    monkeypatch.delenv("QDRANT_HOST", raising=False)
    monkeypatch.delenv("QDRANT_PORT", raising=False)
    monkeypatch.setenv("QDRANT_EMBEDDED", "1")  # force the embedded store, no server
    import src.constants as C
    monkeypatch.setattr(C, "QDRANT_STORAGE_DIR", str(tmp_path / "qd"))
    from src import vector_client
    vector_client.reset_client()
    try:
        c = vector_client.get_vector_client()  # must resolve with no server running
        col = c.get_or_create_collection("m", metadata={"embedding_dimension": 3})
        col.add(ids=["a", "b"],
                documents=["the cat sat", "quantum physics"],
                embeddings=[[0.1, 0.2, 0.3], [0.9, 0.05, 0.02]],
                metadatas=[{"owner": "u1"}, {"owner": "u2"}])
        assert col.count() == 2
        res = col.query(query_embeddings=[[0.1, 0.2, 0.3]], n_results=1)
        assert res["ids"][0] == ["a"]  # nearest neighbour is the matching vector
        # persisted on disk, not :memory:
        assert (tmp_path / "qd").exists()
    finally:
        vector_client.reset_client()


def test_server_mode_when_qdrant_host_set(monkeypatch):
    # QDRANT_HOST selects server mode; an unreachable one must raise, not degrade.
    monkeypatch.setenv("QDRANT_HOST", "127.0.0.1")
    monkeypatch.setenv("QDRANT_PORT", "1")  # nothing listens on port 1
    from src import vector_client
    vector_client.reset_client()
    try:
        with pytest.raises(RuntimeError, match="not reachable"):
            vector_client.get_vector_client()
    finally:
        vector_client.reset_client()
