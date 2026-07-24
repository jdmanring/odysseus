from src.embedding_lanes import (
    EmbeddingLane,
    LANE_CUSTOM,
    LANE_FASTEMBED,
)
from tests.helpers.embedding_lanes import (
    FakeChroma,
    FakeCollection,
    FakeEmbedder,
    FailingEmbedder,
    patch_chroma,
)


def test_memory_vector_store_writes_both_lanes_and_prefers_custom(monkeypatch):
    fake = FakeChroma()
    patch_chroma(monkeypatch, fake)

    import src.embedding_lanes as lanes

    monkeypatch.setattr(lanes, "_build_custom_client", lambda: FakeEmbedder(768, "nomic", "http://embeddings/v1"))
    monkeypatch.setattr(lanes, "_build_local_lane_client", lambda: FakeEmbedder(384, "mini", "local://fastembed"))

    from src.memory_vector import MemoryVectorStore

    store = MemoryVectorStore("data")
    store.add("mem-1", "Nicholai likes direct memory systems")

    assert fake.collections["odysseus_memories_custom"].count() == 1
    assert fake.collections["odysseus_memories_fastembed"].count() == 1

    results = store.search("direct memory", k=5)
    assert results[0]["memory_id"] == "mem-1"
    assert results[0]["embedding_lane"] == LANE_CUSTOM


def test_memory_search_merges_fallback_only_results_before_limit():
    custom_collection = FakeCollection("odysseus_memories_custom", metadata={"embedding_lane": "custom"})
    fast_collection = FakeCollection("odysseus_memories_fastembed", metadata={"embedding_lane": "fastembed"})
    custom_collection.add(
        ids=["old-1", "old-2"],
        embeddings=[[0.0] * 768, [0.0] * 768],
        documents=["older custom memory", "another custom memory"],
        metadatas=[{"source": "memory"}, {"source": "memory"}],
    )
    fast_collection.add(
        ids=["fallback-only"],
        embeddings=[[0.0] * 384],
        documents=["fallback only relevant memory"],
        metadatas=[{"source": "memory"}],
    )

    custom_collection.query = lambda **_kwargs: {
        "ids": [["old-1", "old-2"]],
        "distances": [[0.20, 0.21]],
    }
    fast_collection.query = lambda **_kwargs: {
        "ids": [["fallback-only"]],
        "distances": [[0.05]],
    }

    custom_lane = EmbeddingLane(
        name=LANE_CUSTOM,
        client=FakeEmbedder(768, "nomic", "http://embeddings/v1"),
        collection=custom_collection,
        collection_name="odysseus_memories_custom",
        model="nomic",
        url="http://embeddings/v1",
        dimension=768,
        fingerprint="custom",
    )
    fast_lane = EmbeddingLane(
        name=LANE_FASTEMBED,
        client=FakeEmbedder(384, "mini", "local://fastembed"),
        collection=fast_collection,
        collection_name="odysseus_memories_fastembed",
        model="mini",
        url="local://fastembed",
        dimension=384,
        fingerprint="fast",
    )

    from src.memory_vector import MemoryVectorStore

    store = MemoryVectorStore.__new__(MemoryVectorStore)
    store._lanes = [custom_lane, fast_lane]
    store._healthy = True

    results = store.search("fallback relevant", k=2)

    assert [row["memory_id"] for row in results] == ["fallback-only", "old-1"]


def test_memory_rebuild_does_not_reimport_legacy_collection(monkeypatch):
    fake = FakeChroma()
    legacy = fake.get_or_create_collection("odysseus_memories", metadata={"hnsw:space": "cosine"})
    legacy.add(
        ids=["stale-memory"],
        embeddings=[[0.0] * 384],
        documents=["stale legacy memory"],
        metadatas=[{"source": "memory"}],
    )
    inactive_custom = fake.get_or_create_collection("odysseus_memories_custom", metadata={"embedding_lane": "custom"})
    inactive_custom.add(
        ids=["stale-custom"],
        embeddings=[[0.0] * 768],
        documents=["stale inactive custom memory"],
        metadatas=[{"source": "memory"}],
    )
    patch_chroma(monkeypatch, fake)

    import src.embedding_lanes as lanes

    monkeypatch.setattr(lanes, "_build_custom_client", lambda: None)
    monkeypatch.setattr(lanes, "_build_local_lane_client", lambda: FakeEmbedder(384, "mini", "local://fastembed"))

    from src.memory_vector import MemoryVectorStore

    store = MemoryVectorStore("data")
    assert fake.collections["odysseus_memories_fastembed"].count() == 1

    store.rebuild([{"id": "current-memory", "text": "current rebuilt memory"}])

    assert "odysseus_memories" not in fake.collections
    assert "odysseus_memories_custom" not in fake.collections
    assert fake.collections["odysseus_memories_fastembed"].count() == 1
    assert fake.collections["odysseus_memories_fastembed"].get()["ids"] == ["current-memory"]


def test_memory_remove_deletes_inactive_lane_collection(monkeypatch):
    fake = FakeChroma()
    custom_collection = fake.get_or_create_collection("odysseus_memories_custom", metadata={"embedding_lane": "custom"})
    fast_collection = fake.get_or_create_collection("odysseus_memories_fastembed", metadata={"embedding_lane": "fastembed"})
    custom_collection.add(
        ids=["mem-1"],
        embeddings=[[0.0] * 768],
        documents=["custom stale memory"],
        metadatas=[{"source": "memory"}],
    )
    fast_collection.add(
        ids=["mem-1"],
        embeddings=[[0.0] * 384],
        documents=["fast memory"],
        metadatas=[{"source": "memory"}],
    )
    patch_chroma(monkeypatch, fake)

    fast_lane = EmbeddingLane(
        name=LANE_FASTEMBED,
        client=FakeEmbedder(384, "mini", "local://fastembed"),
        collection=fast_collection,
        collection_name="odysseus_memories_fastembed",
        model="mini",
        url="local://fastembed",
        dimension=384,
        fingerprint="fast",
    )

    from src.memory_vector import MemoryVectorStore

    store = MemoryVectorStore.__new__(MemoryVectorStore)
    store._lanes = [fast_lane]
    store._healthy = True

    store.remove("mem-1")

    assert custom_collection.count() == 0
    assert fast_collection.count() == 0


def _lane_over(collection, dim=384):
    return EmbeddingLane(
        name=LANE_FASTEMBED,
        client=FakeEmbedder(dim, "mini", "local://fastembed"),
        collection=collection,
        collection_name=collection.name,
        model="mini",
        url="local://fastembed",
        dimension=dim,
        fingerprint="fast",
    )


def test_memory_search_makes_no_count_round_trips():
    # count() is an HTTP round-trip per call in server mode; the pre-flight
    # guards it once powered cost ~10 ms per search. Empty collections just
    # return no hits, so search must never call count().
    collection = FakeCollection("odysseus_memories_fastembed", metadata={"embedding_lane": "fastembed"})
    collection.add(
        ids=["mem-1"],
        embeddings=[[0.0] * 384],
        documents=["a memory"],
        metadatas=[{"source": "memory"}],
    )
    count_calls = []
    original_count = collection.count
    collection.count = lambda: count_calls.append(1) or original_count()

    from src.memory_vector import MemoryVectorStore

    store = MemoryVectorStore.__new__(MemoryVectorStore)
    store._lanes = [_lane_over(collection)]
    store._healthy = True

    results = store.search("anything", k=3)
    assert results and results[0]["memory_id"] == "mem-1"
    assert count_calls == []

    assert store.find_similar("a memory", threshold=0.0) == "mem-1"
    assert count_calls == []


def test_memory_search_on_empty_store_returns_empty_without_error():
    collection = FakeCollection("odysseus_memories_fastembed", metadata={"embedding_lane": "fastembed"})

    from src.memory_vector import MemoryVectorStore

    store = MemoryVectorStore.__new__(MemoryVectorStore)
    store._lanes = [_lane_over(collection)]
    store._healthy = True

    assert store.search("anything", k=3) == []
    assert store.find_similar("anything") is None


def test_memory_search_embeds_query_with_query_prefix():
    # nomic is prefix-trained: stored docs carry search_document:, so the
    # search side must encode with is_query=True (search_query: prefix).
    collection = FakeCollection("odysseus_memories_fastembed", metadata={"embedding_lane": "fastembed"})
    collection.add(
        ids=["mem-1"],
        embeddings=[[0.0] * 384],
        documents=["a memory"],
        metadatas=[{"source": "memory"}],
    )

    class RecordingEmbedder(FakeEmbedder):
        def __init__(self, *args):
            super().__init__(*args)
            self.query_flags = []

        def encode(self, texts, normalize_embeddings=True, is_query=False):
            self.query_flags.append(is_query)
            return super().encode(texts, normalize_embeddings, is_query)

    embedder = RecordingEmbedder(384, "mini", "local://fastembed")
    lane = _lane_over(collection)
    lane.client = embedder

    from src.memory_vector import MemoryVectorStore

    store = MemoryVectorStore.__new__(MemoryVectorStore)
    store._lanes = [lane]
    store._healthy = True

    store.search("anything", k=3)
    assert embedder.query_flags == [True]

    embedder.query_flags.clear()
    store.find_similar("a memory")  # doc-to-doc: must NOT use the query prefix
    assert embedder.query_flags == [False]


def test_memory_rebuild_continues_when_custom_lane_fails(monkeypatch):
    fake = FakeChroma()
    patch_chroma(monkeypatch, fake)

    import src.embedding_lanes as lanes

    monkeypatch.setattr(lanes, "_build_custom_client", lambda: FailingEmbedder(768, "nomic", "http://embeddings/v1"))
    monkeypatch.setattr(lanes, "_build_local_lane_client", lambda: FakeEmbedder(384, "mini", "local://fastembed"))

    from src.memory_vector import MemoryVectorStore

    store = MemoryVectorStore("data")
    store.rebuild([{"id": "current-memory", "text": "current rebuilt memory"}])

    assert fake.collections["odysseus_memories_custom"].count() == 0
    assert fake.collections["odysseus_memories_fastembed"].count() == 1
    assert fake.collections["odysseus_memories_fastembed"].get()["ids"] == ["current-memory"]
