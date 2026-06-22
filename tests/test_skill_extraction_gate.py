"""
Verify the extraction gate thresholds and auto-approve default introduced by
fix(skills): raise extraction threshold, align confidence floor, default
auto-approve to draft.

Gate now requires rounds >= 2 AND tools >= 3 (was rounds >= 2 OR tools >= 2).
MIN_CONFIDENCE raised from 0.6 to 0.85 (aligned with injection floor).
auto_approve_skills default changed from True to False (skills land as drafts).
"""
import pytest

from services.memory import skill_extractor

_GOOD_RESPONSE = (
    '{"title": "Deploy runbook", "problem": "manual deploys are error-prone", '
    '"solution": "use the deploy script", "steps": ["build", "push", "restart"], '
    '"tags": ["deploy"], "confidence": 0.9}'
)

_LOW_CONFIDENCE_RESPONSE = (
    '{"title": "Low confidence skill", "problem": "p", "solution": "s", '
    '"steps": ["one", "two", "three"], "tags": ["test"], "confidence": 0.84}'
)


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


async def _call_extractor(monkeypatch, response, round_count, tool_count):
    async def fake_llm(*a, **k):
        return response

    monkeypatch.setattr("src.llm_core.llm_call_async", fake_llm)
    sm = _FakeSkillsManager()
    entry = await skill_extractor.maybe_extract_skill(
        _FakeSession(), sm,
        endpoint_url="http://endpoint",
        model="test-model",
        headers={},
        round_count=round_count,
        tool_count=tool_count,
        owner="alice",
    )
    return entry, sm


async def test_gate_skips_when_rounds_low_tools_below_three(monkeypatch):
    """rounds=1, tools=2 → skipped (rounds < 2, fails new AND gate)."""
    entry, sm = await _call_extractor(monkeypatch, _GOOD_RESPONSE, round_count=1, tool_count=2)
    assert entry is None
    assert not sm.added


async def test_gate_skips_when_tools_below_three(monkeypatch):
    """rounds=2, tools=2 → skipped (tools < 3, fails new AND gate)."""
    entry, sm = await _call_extractor(monkeypatch, _GOOD_RESPONSE, round_count=2, tool_count=2)
    assert entry is None
    assert not sm.added


async def test_gate_passes_at_new_combined_threshold(monkeypatch):
    """rounds=2, tools=3 → extraction proceeds."""
    entry, sm = await _call_extractor(monkeypatch, _GOOD_RESPONSE, round_count=2, tool_count=3)
    assert entry is not None
    assert sm.added and sm.added[0]["title"] == "Deploy runbook"


async def test_low_confidence_dropped_at_new_floor(monkeypatch):
    """confidence=0.84 → dropped (below new MIN_CONFIDENCE=0.85)."""
    entry, sm = await _call_extractor(monkeypatch, _LOW_CONFIDENCE_RESPONSE, round_count=2, tool_count=3)
    assert entry is None
    assert not sm.added


async def test_auto_approve_default_is_draft(monkeypatch):
    """With no prefs override, auto_approve_skills defaults to False → status is 'draft'."""
    # Prevent prefs lookup from finding anything
    monkeypatch.setattr(
        "routes.prefs_routes._load_for_user",
        lambda owner: {},
        raising=False,
    )

    entry, sm = await _call_extractor(monkeypatch, _GOOD_RESPONSE, round_count=2, tool_count=3)
    assert entry is not None
    assert sm.added[0].get("status") == "draft"
