"""
Tests for feat/skill-quality-signals (jdmanring/odysseus#87).

Verifies:
  1. BM25 ranks a distinctive-vocabulary skill above a generic skill for a
     specific query.
  2. BM25 returns 0 for a query with no corpus overlap.
  3. Hybrid get_relevant_skills() with empty skills list → empty result, no
     exception.
  4. _health_score returns 100 for an ideal (pass, high-confidence, used,
     necessary) skill.
  5. _health_score returns < 30 for a failed, unused, unnecessary skill.
  6. _health_score handles None/missing fields without raising.

Research basis:
  SkillRet (arxiv:2605.05726, 2025): BM25 hybrid outperforms pure Jaccard.
  SkillOps (arxiv:2605.13716, 2025): five diagnostic dimensions mapped to
  existing Odysseus sidecar fields.
"""
import tempfile
from pathlib import Path

from services.memory.skills import (
    SkillsManager,
    _bm25_score,
    _compute_idf,
    _health_score,
    _tokenize,
)


# ── BM25 retrieval ────────────────────────────────────────────────────────────

_DISTINCTIVE = {
    "name": "configure-libvirt-xml-bridge",
    "description": "Configure libvirt bridge networking via XML definition",
    "when_to_use": "When setting up libvirt virtual machine bridge networking",
    "tags": ["libvirt", "xml", "bridge", "networking"],
    "procedure": ["virsh net-define bridge.xml", "virsh net-start bridge"],
    "status": "published",
    "confidence": 0.95,
    "source": "learned",
}

_GENERIC = {
    "name": "configure-settings",
    "description": "Configure application settings",
    "when_to_use": "When you need to change settings",
    "tags": ["config", "settings"],
    "procedure": ["Open settings panel", "Adjust values", "Save"],
    "status": "published",
    "confidence": 0.85,
    "source": "learned",
}


def _skill_text(sk):
    return " ".join([
        sk.get("name", ""),
        sk.get("description", ""),
        sk.get("when_to_use", ""),
        " ".join(sk.get("tags", []) or []),
    ])


def test_bm25_ranks_distinctive_skill_higher():
    """BM25 scores a skill with distinctive vocabulary higher than a generic
    skill when the query uses that distinctive vocabulary."""
    skills = [_DISTINCTIVE, _GENERIC]
    idf = _compute_idf(skills)

    query_tokens = _tokenize("configure libvirt xml bridge networking")
    distinctive_tokens = list(_tokenize(_skill_text(_DISTINCTIVE)))
    generic_tokens = list(_tokenize(_skill_text(_GENERIC)))

    score_distinctive = _bm25_score(query_tokens, distinctive_tokens, idf)
    score_generic = _bm25_score(query_tokens, generic_tokens, idf)

    assert score_distinctive > score_generic, (
        f"Expected distinctive skill ({score_distinctive:.3f}) > "
        f"generic ({score_generic:.3f}) for a libvirt-specific query"
    )


def test_bm25_returns_zero_for_no_overlap():
    """BM25 returns 0 when query has no tokens in common with the skill corpus."""
    skills = [_DISTINCTIVE, _GENERIC]
    idf = _compute_idf(skills)

    query_tokens = _tokenize("xylophone banana thermodynamics")
    skill_tokens = list(_tokenize(_skill_text(_DISTINCTIVE)))

    score = _bm25_score(query_tokens, skill_tokens, idf)
    assert score == 0.0, f"Expected 0.0 for no-overlap query, got {score}"


def test_hybrid_get_relevant_skills_empty_list():
    """get_relevant_skills with an empty skills list returns [] without raising."""
    with tempfile.TemporaryDirectory() as tmp:
        sm = SkillsManager(tmp)
        result = sm.get_relevant_skills("configure libvirt bridge", skills=[])
        assert result == []


def test_hybrid_get_relevant_skills_retrieves_distinctive():
    """get_relevant_skills retrieves the distinctive skill over the generic one
    for a specific query."""
    with tempfile.TemporaryDirectory() as tmp:
        sm = SkillsManager(tmp)
        result = sm.get_relevant_skills(
            "configure libvirt xml bridge networking",
            skills=[_DISTINCTIVE, _GENERIC],
            threshold=0.0,
            max_items=2,
        )
        assert len(result) > 0
        assert result[0]["name"] == "configure-libvirt-xml-bridge", (
            f"Expected distinctive skill first, got {result[0]['name']!r}"
        )


# ── Health score ──────────────────────────────────────────────────────────────

def test_health_score_ideal_skill_is_100():
    """Ideal skill (confidence=1.0, pass audit, 20+ uses, necessary) scores 100."""
    sk = {
        "confidence": 1.0,
        "audit_verdict": "pass",
        "uses": 20,
        "necessity": {"necessary": True, "reason": "unique procedure"},
    }
    assert _health_score(sk) == 100


def test_health_score_failed_skill_is_low():
    """Failed, unused, unnecessary skill scores < 30."""
    sk = {
        "confidence": 0.35,
        "audit_verdict": "fail",
        "uses": 0,
        "necessity": {"necessary": False, "reason": "redundant"},
    }
    score = _health_score(sk)
    assert score < 30, f"Expected < 30 for failed/unused/unnecessary skill, got {score}"


def test_health_score_handles_missing_fields():
    """_health_score must not raise for None or missing fields."""
    cases = [
        {},
        {"confidence": None, "audit_verdict": None, "uses": None, "necessity": None},
        {"confidence": "not-a-number"},
    ]
    for sk in cases:
        score = _health_score(sk)
        assert 0 <= score <= 100, f"Expected 0–100, got {score} for {sk}"


def test_idf_cache_is_keyed_to_corpus_not_stale_across_subsets():
    """The BM25 IDF cache must recompute when a *different* corpus is passed.

    Callers pass owner/status-filtered subsets to the same SkillsManager; a cache
    invalidated only on library mutations would apply one corpus's IDF to another
    and silently skew ranking. Verify the cache re-keys on the corpus identity.
    """
    import tempfile
    from services.memory.skills import SkillsManager

    with tempfile.TemporaryDirectory() as d:
        sm = SkillsManager(data_dir=d)

        corpus_a = [_DISTINCTIVE, _GENERIC]
        sm.get_relevant_skills("configure libvirt xml bridge", skills=corpus_a)
        key_a = sm._idf_cache[0]
        assert key_a == frozenset(s.get("id") or s.get("name", "") for s in corpus_a)

        # A different (subset) corpus must recompute — not reuse corpus A's IDF.
        corpus_b = [_GENERIC]
        sm.get_relevant_skills("configure settings", skills=corpus_b)
        key_b = sm._idf_cache[0]
        assert key_b == frozenset(s.get("id") or s.get("name", "") for s in corpus_b)
        assert key_b != key_a, "IDF cache did not re-key on a different corpus (stale)"
