import pytest

from src.embedding_lanes import (
    LANE_CUSTOM,
    LANE_FASTEMBED,
    build_embedding_lanes,
)
from tests.helpers.embedding_lanes import (
    FakeVectorStore,
    FakeEmbedder,
    patch_vector_store,
)


def test_build_embedding_lanes_keeps_custom_and_fastembed_dimensions_separate(monkeypatch):
    fake = FakeVectorStore()
    patch_vector_store(monkeypatch, fake)

    import src.embedding_lanes as lanes

    monkeypatch.setattr(
        lanes,
        "_build_custom_client",
        lambda: FakeEmbedder(768, "nomic-embed-text", "http://embeddings/v1"),
    )
    monkeypatch.setattr(
        lanes,
        "_build_local_lane_client",
        lambda: FakeEmbedder(384, "sentence-transformers/all-MiniLM-L6-v2", "local://fastembed"),
    )

    built = build_embedding_lanes("odysseus_memories")

    assert [lane.name for lane in built] == [LANE_CUSTOM, LANE_FASTEMBED]
    assert built[0].collection_name == "odysseus_memories_custom"
    assert built[0].dimension == 768
    assert built[1].collection_name == "odysseus_memories_fastembed"
    assert built[1].dimension == 384

    built[0].collection.add(ids=["custom"], embeddings=built[0].encode(["a"]), documents=["a"])
    built[1].collection.add(ids=["fast"], embeddings=built[1].encode(["a"]), documents=["a"])

    with pytest.raises(RuntimeError, match="dimension"):
        built[0].collection.query(query_embeddings=built[1].encode(["bad"]), n_results=1)


def test_build_embedding_lanes_recreates_collection_on_fingerprint_change(monkeypatch):
    """A changed embedding fingerprint drops and recreates the lane's collection
    empty — no preservation or re-embed (nothing persisted worth keeping)."""
    fake = FakeVectorStore()
    old_custom = fake.get_or_create_collection(
        "odysseus_rag_custom", metadata={"embedding_dimension": 768})
    old_custom.add(ids=["old"], embeddings=[[0.0] * 768], documents=["old"])
    patch_vector_store(monkeypatch, fake)

    import src.embedding_lanes as lanes

    # Sidecar records a stale fingerprint for the custom collection only; the
    # fastembed collection has no recorded fingerprint (adopted as-is).
    monkeypatch.setattr(lanes, "_read_fingerprints", lambda: {"odysseus_rag_custom": "stale"})
    written = {}
    monkeypatch.setattr(lanes, "_write_fingerprint", lambda name, fp: written.__setitem__(name, fp))
    monkeypatch.setattr(lanes, "_build_custom_client", lambda: FakeEmbedder(1024, "bge-large", "http://embeddings/v1"))
    monkeypatch.setattr(lanes, "_build_local_lane_client", lambda: FakeEmbedder(384, "mini", "local://fastembed"))

    built = build_embedding_lanes("odysseus_rag")

    # Custom: fingerprint changed -> dropped and recreated EMPTY at the new dim.
    assert "odysseus_rag_custom" in fake.deleted
    assert fake.collections["odysseus_rag_custom"].count() == 0
    assert built[0].dimension == 1024
    # The recreated collection's new fingerprint is persisted.
    assert "odysseus_rag_custom" in written


def test_build_embedding_lanes_adopts_collection_when_fingerprint_matches(monkeypatch):
    """A matching fingerprint leaves the existing collection (and its rows) in place."""
    fake = FakeVectorStore()
    patch_vector_store(monkeypatch, fake)

    import src.embedding_lanes as lanes

    client = FakeEmbedder(768, "nomic", "http://embeddings/v1")
    fp = lanes._fingerprint(LANE_CUSTOM, client.url, client.model, 768)
    existing = fake.get_or_create_collection(
        "odysseus_rag_custom", metadata={"embedding_dimension": 768})
    existing.add(ids=["keep"], embeddings=[[0.0] * 768], documents=["keep"])

    monkeypatch.setattr(lanes, "_read_fingerprints", lambda: {"odysseus_rag_custom": fp})
    monkeypatch.setattr(lanes, "_write_fingerprint", lambda *a: None)
    monkeypatch.setattr(lanes, "_build_custom_client", lambda: client)

    def fail_fastembed():
        raise RuntimeError("fastembed missing")

    monkeypatch.setattr(lanes, "_build_local_lane_client", fail_fastembed)

    built = build_embedding_lanes("odysseus_rag")

    assert [lane.name for lane in built] == [LANE_CUSTOM]
    assert "odysseus_rag_custom" not in fake.deleted
    assert fake.collections["odysseus_rag_custom"].count() == 1


def test_build_embedding_lanes_uses_fastembed_when_custom_unavailable(monkeypatch):
    fake = FakeVectorStore()
    patch_vector_store(monkeypatch, fake)

    import src.embedding_lanes as lanes

    def fail_custom():
        raise RuntimeError("down")

    monkeypatch.setattr(lanes, "_build_custom_client", fail_custom)
    monkeypatch.setattr(lanes, "_build_local_lane_client", lambda: FakeEmbedder(384, "mini", "local://fastembed"))

    built = build_embedding_lanes("odysseus_tool_index")

    assert [lane.name for lane in built] == [LANE_FASTEMBED]
    assert built[0].collection_name == "odysseus_tool_index_fastembed"


def test_custom_lane_preserves_default_embedding_client_probe(monkeypatch):
    import src.embedding_lanes as lanes
    import src.embeddings as embeddings

    embeddings.reset_http_embed_state()
    monkeypatch.setattr(lanes, "_load_custom_endpoint", lambda: {})

    calls = []

    class DefaultClient(FakeEmbedder):
        def __init__(self, url=None, model=None, api_key=None):
            calls.append({"url": url, "model": model, "api_key": api_key})
            super().__init__(768, model or "all-minilm:l6-v2", url or "http://localhost:11434/v1/embeddings")

    monkeypatch.setattr(embeddings, "EmbeddingClient", DefaultClient)

    client = lanes._build_custom_client()

    assert calls == [{"url": None, "model": None, "api_key": None}]
    assert client.url == "http://localhost:11434/v1/embeddings"
    embeddings.reset_http_embed_state()


def test_custom_lane_uses_http_down_latch(monkeypatch):
    import src.embedding_lanes as lanes
    import src.embeddings as embeddings

    embeddings.reset_http_embed_state()
    calls = []

    class DownClient:
        def __init__(self, url=None, model=None, api_key=None):
            calls.append({"url": url, "model": model, "api_key": api_key})

        def get_sentence_embedding_dimension(self):
            raise RuntimeError("endpoint down")

    class LocalFastEmbed(FakeEmbedder):
        def __init__(self):
            super().__init__(384, "mini", "local://fastembed")

    monkeypatch.setattr(embeddings, "EmbeddingClient", DownClient)
    monkeypatch.setattr(embeddings, "FastEmbedClient", LocalFastEmbed)

    with pytest.raises(RuntimeError, match="HTTP embedding lane unavailable"):
        lanes._build_custom_client()
    with pytest.raises(RuntimeError, match="HTTP embedding lane unavailable"):
        lanes._build_custom_client()

    assert calls == [{"url": None, "model": None, "api_key": None}]
    embeddings.reset_http_embed_state()
