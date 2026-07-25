"""Write-time supersede: two-tier policy pinned to the measured thresholds.

Doc-doc cosine cannot separate true supersede pairs from distinct-but-similar
facts (see src/memory_supersede.py for the measured distributions), so the
AUTO tier applies only at >= 0.80 (zero measured false positives) and the
0.70-0.80 band is surfaced as candidates for explicit confirmation. These
tests pin that policy plus the invariants: history preserved, vector index
cleared, no cross-owner supersede, recall paths never resurface stale.
"""
import json
import os

import pytest

from src import memory_supersede
from src.memory import MemoryManager


class FakeVector:
    healthy = True

    def __init__(self, matches=None):
        self.matches = matches or []
        self.removed = []
        self.added = []

    def similar(self, text, k=5, floor=0.0):
        return [m for m in self.matches if m["similarity"] >= floor][:k]

    def search(self, query, k=8):
        return []

    def remove(self, memory_id):
        self.removed.append(memory_id)

    def add(self, memory_id, text):
        self.added.append(memory_id)


@pytest.fixture
def manager(tmp_path):
    mgr = MemoryManager(str(tmp_path))
    return mgr


def _seed(manager, rows):
    entries = []
    for mid, text, owner in rows:
        e = manager.add_entry(text, owner=owner)
        e["id"] = mid
        entries.append(e)
    manager.save(entries)
    return entries


def _entry(manager, mid):
    return next(e for e in manager.load_all() if e["id"] == mid)


def test_auto_tier_supersedes_and_clears_vector(manager, monkeypatch):
    monkeypatch.delenv("ODYSSEUS_MEMORY_SUPERSEDE", raising=False)
    _seed(manager, [("old1", "The user drinks black coffee.", "james")])
    vec = FakeVector([{"memory_id": "old1", "similarity": 0.86}])
    new = manager.add_entry("The user switched to green tea.", owner="james")

    result = memory_supersede.on_write(manager, vec, new)

    assert result["superseded"] == ["old1"]
    assert result["candidates"] == []
    assert vec.removed == ["old1"]
    stored = _entry(manager, "old1")
    assert stored["superseded_by"] == new["id"]
    assert stored["superseded_at"] > 0
    assert stored["text"] == "The user drinks black coffee."  # history intact


def test_suggest_tier_returns_candidates_without_applying(manager):
    _seed(manager, [("old1", "The user works at a design agency.", "james")])
    vec = FakeVector([{"memory_id": "old1", "similarity": 0.75}])
    new = manager.add_entry("The user works at a robotics startup.", owner="james")

    result = memory_supersede.on_write(manager, vec, new)

    assert result["superseded"] == []
    assert [c["id"] for c in result["candidates"]] == ["old1"]
    assert result["candidates"][0]["similarity"] == 0.75
    assert vec.removed == []
    assert "superseded_by" not in _entry(manager, "old1")


def test_cross_owner_never_superseded_or_suggested(manager):
    _seed(manager, [("old1", "The user likes hiking.", "alice")])
    vec = FakeVector([{"memory_id": "old1", "similarity": 0.95}])
    new = manager.add_entry("The user likes hiking a lot.", owner="james")

    result = memory_supersede.on_write(manager, vec, new)

    assert result == {"superseded": [], "candidates": []}
    assert "superseded_by" not in _entry(manager, "old1")


def test_kill_switch_disables_everything(manager, monkeypatch):
    monkeypatch.setenv("ODYSSEUS_MEMORY_SUPERSEDE", "0")
    _seed(manager, [("old1", "fact", "james")])
    vec = FakeVector([{"memory_id": "old1", "similarity": 0.99}])
    new = manager.add_entry("fact restated", owner="james")

    assert memory_supersede.on_write(manager, vec, new) == \
        {"superseded": [], "candidates": []}


def test_apply_validates_self_missing_and_already_superseded(manager):
    entries = _seed(manager, [
        ("a", "fact a", "james"),
        ("b", "fact b", "james"),
    ])
    entries[1]["superseded_by"] = "a"
    manager.save(entries)
    vec = FakeVector()

    applied = memory_supersede.apply(
        manager, vec, "a", ["a", "b", "ghost"], owner="james")

    # self-supersede, already-superseded, and unknown ids are all rejected
    assert applied == []
    assert vec.removed == []


def test_apply_marks_and_removes(manager):
    _seed(manager, [("a", "old fact", "james"), ("b", "other", "james")])
    vec = FakeVector()

    applied = memory_supersede.apply(manager, vec, "new-id", ["a"], owner="james")

    assert applied == ["a"]
    assert vec.removed == ["a"]
    assert _entry(manager, "a")["superseded_by"] == "new-id"
    assert "superseded_by" not in _entry(manager, "b")


def test_keyword_fallback_filters_superseded(manager):
    entries = _seed(manager, [
        ("old", "The user drinks black coffee every morning.", None),
        ("new", "The user drinks green tea every morning.", None),
    ])
    entries[0]["superseded_by"] = "new"
    manager.save(entries)

    hits = manager.get_relevant_memories(
        "what does the user drink every morning", manager.load_all())
    ids = [h["id"] for h in hits]
    assert "new" in ids and "old" not in ids


def test_unhealthy_vector_is_a_noop(manager):
    vec = FakeVector([{"memory_id": "x", "similarity": 0.99}])
    vec.healthy = False
    new = manager.add_entry("anything", owner="james")
    assert memory_supersede.on_write(manager, vec, new) == \
        {"superseded": [], "candidates": []}


def test_thresholds_match_measured_operating_points():
    # 0.80 = zero measured false positives on trap/cross pairs; 0.70 = 0.96
    # supersede recall floor for the SUGGEST tier. If these move, re-run the
    # threshold probe against the labeled pairs before shipping.
    assert memory_supersede.AUTO_THRESHOLD == 0.80
    assert memory_supersede.SUGGEST_THRESHOLD == 0.70
