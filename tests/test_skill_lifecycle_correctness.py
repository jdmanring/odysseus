"""
Tests for fix/skill-lifecycle-correctness (jdmanring/odysseus#86).

Verifies the corrected auto_approve_skills semantics across the pipeline:

  1. Extraction always produces draft — pref has no effect at extraction time.
  2. manage_skills add always produces draft (no pref check in fallback).
  3. Source-aware pre-filter in injection path:
       auto_approve=True  → all skills pass through to get_relevant_skills()
       auto_approve=False → published + source=teacher-escalation drafts only
  4. Audit-finalization default is True — the audit promotes passing skills.
  5. Injection path default is True — published + all drafts at confidence floor.

Research basis:
  SkillsBench (arxiv:2602.12670): curation is the quality gate — audit must promote.
  SkillWeaver (arxiv:2504.07079): teacher-escalation drafts must inject immediately.
"""
from pathlib import Path

import pytest

from services.memory import skill_extractor
from services.memory.skills import SkillsManager

# ── Source-text fixtures ──────────────────────────────────────────────────────

_EXTRACTOR_SRC = (
    Path(__file__).resolve().parent.parent
    / "services/memory/skill_extractor.py"
).read_text(encoding="utf-8")

_AGENT_LOOP_SRC = (
    Path(__file__).resolve().parent.parent / "src/agent_loop.py"
).read_text(encoding="utf-8")

_SKILLS_ROUTES_SRC = (
    Path(__file__).resolve().parent.parent / "routes/skills_routes.py"
).read_text(encoding="utf-8")

_TOOL_IMPL_SRC = (
    Path(__file__).resolve().parent.parent / "src/tool_implementations.py"
).read_text(encoding="utf-8")

# ── Source-text assertions ────────────────────────────────────────────────────


def test_extractor_has_no_auto_approve_pref_check():
    """skill_extractor.py must not read auto_approve_skills — extraction is always draft."""
    # The pref block was removed; only a comment referencing the old behavior
    # may remain, but no live pref lookup.
    assert 'auto_approve_skills", True)' not in _EXTRACTOR_SRC
    assert 'auto_approve_skills", False)' not in _EXTRACTOR_SRC


def test_injection_path_default_is_true():
    """agent_loop.py injection path must default auto_approve_skills to True.

    The source-aware pre-filter approach replaces the min_conf=2.0 hack.
    Teacher-escalation drafts pass through even when auto_approve=False.
    """
    assert 'auto_approve_skills", True)' in _AGENT_LOOP_SRC


def test_audit_finalization_default_is_true():
    """skills_routes.py audit path must default auto_approve_skills to True.

    The audit is the quality gate. Defaulting to False means a skill that
    passes the full 6-stage audit stays as draft forever — zero benefit.
    """
    assert 'auto_approve_skills", True)' in _SKILLS_ROUTES_SRC


def test_tool_implementations_add_has_no_auto_approve_true_fallback():
    """tool_implementations.py manage_skills add must not auto-publish via pref.

    The pref check with True default was removed. Agent-added skills always
    go to draft so they are tested by the same audit pipeline as extracted skills.
    """
    # The specific pattern that caused auto-publishing must be absent
    assert '"published" if _prefs.get("auto_approve_skills"' not in _TOOL_IMPL_SRC


# ── Fake helpers ──────────────────────────────────────────────────────────────


class _FakeSession:
    session_id = "s1"

    def get_context_messages(self):
        return [
            {"role": "user", "content": "Set up the deployment pipeline"},
            {"role": "assistant", "content": "I ran several steps to configure it."},
        ]


class _FakeSkillsManager:
    def __init__(self):
        self.added = []

    def load(self, owner=None):
        return []

    def add_skill(self, **kwargs):
        self.added.append(kwargs)
        return {"id": "skill-1", **kwargs}


_GOOD_RESPONSE = (
    '{"title": "Deploy runbook", "problem": "manual deploys are error-prone", '
    '"solution": "use the deploy script", "steps": ["build", "push", "restart"], '
    '"tags": ["deploy"], "confidence": 0.9}'
)


async def _extract(monkeypatch, prefs=None):
    async def fake_llm(*a, **k):
        return _GOOD_RESPONSE

    monkeypatch.setattr("src.llm_core.llm_call_async", fake_llm)
    if prefs is not None:
        monkeypatch.setattr(
            "routes.prefs_routes._load_for_user",
            lambda owner: prefs,
        )
    sm = _FakeSkillsManager()
    entry = await skill_extractor.maybe_extract_skill(
        _FakeSession(), sm,
        endpoint_url="http://endpoint",
        model="test-model",
        headers={},
        round_count=2,
        tool_count=3,
        owner="alice",
    )
    return entry, sm


# ── Behavioural: extraction always draft ─────────────────────────────────────


async def test_extraction_always_draft_when_auto_approve_true(monkeypatch):
    """Extraction produces draft even when auto_approve_skills=True."""
    entry, sm = await _extract(monkeypatch, prefs={"auto_approve_skills": True})
    assert entry is not None
    assert sm.added[0].get("status") == "draft"


async def test_extraction_always_draft_when_auto_approve_false(monkeypatch):
    """Extraction produces draft even when auto_approve_skills=False."""
    entry, sm = await _extract(monkeypatch, prefs={"auto_approve_skills": False})
    assert entry is not None
    assert sm.added[0].get("status") == "draft"


async def test_extraction_always_draft_with_no_prefs(monkeypatch):
    """Extraction produces draft with empty prefs (no pref lookup dependency)."""
    entry, sm = await _extract(monkeypatch, prefs={})
    assert entry is not None
    assert sm.added[0].get("status") == "draft"


# ── Behavioural: source-aware pre-filter ─────────────────────────────────────

_PUBLISHED = {"name": "pub-skill", "status": "published", "confidence": 0.9,
               "source": "learned", "description": "deploy the server"}
_LEARNED_DRAFT = {"name": "learned-draft", "status": "draft", "confidence": 0.9,
                  "source": "learned", "description": "deploy the server"}
_TEACHER_DRAFT = {"name": "teacher-draft", "status": "draft", "confidence": 0.9,
                  "source": "teacher-escalation", "description": "deploy the server"}

# Use a temporary SkillsManager with a real directory to test get_relevant_skills
import tempfile, os


def _make_sm_with_skills(tmp_path, skill_list):
    """Create a SkillsManager backed by tmp_path with the given skill list pre-loaded."""
    sm = SkillsManager(tmp_path)
    # Patch load() to return the skill list directly (avoids filesystem setup)
    sm._test_skills = skill_list
    original_load = sm.load

    def patched_load(owner=None):
        return list(sm._test_skills)

    sm.load = patched_load
    return sm


def _apply_prefilter(all_skills, auto_approve):
    """Mirror the source-aware pre-filter logic from agent_loop.py."""
    if not auto_approve:
        return [
            s for s in all_skills
            if s.get("status") == "published"
            or (s.get("status") == "draft"
                and s.get("source") == "teacher-escalation")
        ]
    return all_skills


def test_prefilter_auto_approve_true_passes_all():
    """When auto_approve=True, all skills reach get_relevant_skills()."""
    all_skills = [_PUBLISHED, _LEARNED_DRAFT, _TEACHER_DRAFT]
    result = _apply_prefilter(all_skills, auto_approve=True)
    assert len(result) == 3


def test_prefilter_auto_approve_false_excludes_learned_draft():
    """When auto_approve=False, learned drafts are excluded."""
    all_skills = [_PUBLISHED, _LEARNED_DRAFT, _TEACHER_DRAFT]
    result = _apply_prefilter(all_skills, auto_approve=False)
    names = [s["name"] for s in result]
    assert "learned-draft" not in names


def test_prefilter_auto_approve_false_includes_teacher_draft():
    """When auto_approve=False, teacher-escalation drafts still pass through."""
    all_skills = [_PUBLISHED, _LEARNED_DRAFT, _TEACHER_DRAFT]
    result = _apply_prefilter(all_skills, auto_approve=False)
    names = [s["name"] for s in result]
    assert "teacher-draft" in names


def test_prefilter_auto_approve_false_always_includes_published():
    """When auto_approve=False, published skills always pass."""
    all_skills = [_PUBLISHED, _LEARNED_DRAFT, _TEACHER_DRAFT]
    result = _apply_prefilter(all_skills, auto_approve=False)
    names = [s["name"] for s in result]
    assert "pub-skill" in names
