"""Shared BM25 + dense fusion used by every non-chat memory recall path."""
import time

from src.memory_ranking import bm25_scores, hybrid_search


def _e(mid, text, ts=None, **kw):
    return {"id": mid, "text": text,
            "timestamp": ts if ts is not None else int(time.time()), **kw}


class FakeVector:
    healthy = True

    def __init__(self, scores):
        self._scores = scores

    def search(self, query, k=8):
        return [{"memory_id": m, "score": s} for m, s in self._scores.items()]


def test_bm25_rare_term_beats_common_term():
    entries = [
        _e("a", "the user keeps a spare key with the neighbor"),
        _e("b", "the user the user the user talks a lot"),
        _e("c", "groceries arrive on thursday"),
    ]
    scores = bm25_scores("where is the spare key", entries)
    assert scores["a"] == 1.0  # per-query max normalization
    assert scores.get("b", 0.0) < scores["a"]
    assert "c" not in scores


def test_bm25_empty_inputs():
    assert bm25_scores("", [_e("a", "text")]) == {}
    assert bm25_scores("query", []) == {}


def test_hybrid_filters_superseded_even_with_high_vector_score():
    entries = [
        _e("stale", "user drinks coffee", superseded_by="fresh"),
        _e("fresh", "user drinks green tea"),
    ]
    vec = FakeVector({"stale": 0.99, "fresh": 0.60})
    ranked = hybrid_search("what does the user drink", entries, vec, k=5)
    ids = [e["id"] for _, e in ranked]
    assert ids == ["fresh"]


def test_hybrid_gate_requires_relevance_not_recency():
    entries = [_e("r", "completely unrelated purple elephants", ts=int(time.time()))]
    vec = FakeVector({"r": 0.05})
    assert hybrid_search("what is the wifi password", entries, vec, k=5) == []


def test_hybrid_without_vector_ranks_by_lexical():
    entries = [
        _e("hit", "the wifi password is stored in the vault"),
        _e("miss", "the user enjoys long walks"),
    ]
    ranked = hybrid_search("wifi password", entries, memory_vector=None, k=5)
    ids = [e["id"] for _, e in ranked]
    assert ids == ["hit"]


def test_hybrid_vector_failure_degrades_to_lexical():
    class BrokenVector:
        healthy = True

        def search(self, query, k=8):
            raise RuntimeError("backend down")

    entries = [_e("hit", "the wifi password is stored in the vault")]
    ranked = hybrid_search("wifi password", entries, BrokenVector(), k=5)
    assert [e["id"] for _, e in ranked] == ["hit"]


def test_hybrid_deterministic_tiebreak():
    ts = int(time.time())
    entries = [_e("b", "identical text here", ts), _e("a", "identical text here", ts)]
    ranked = hybrid_search("identical text", entries, memory_vector=None, k=5)
    assert [e["id"] for _, e in ranked] == ["a", "b"]
