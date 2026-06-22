"""
Verify the extraction gate thresholds and auto-approve defaults introduced by
fix(skills): raise extraction threshold, align confidence floor, default
auto-approve to draft.

Gate now requires rounds >= 2 AND tools >= 3 (was rounds >= 2 OR tools >= 2).
MIN_CONFIDENCE raised from 0.6 to 0.85 (aligned with injection floor).
auto_approve_skills default changed to False in extractor, injection path, and
audit-finalization path — skills land as drafts until the user publishes them.
"""
from pathlib import Path

import pytest

from services.memory import skill_extractor

# ── Source-text fixtures ──────────────────────────────────────────────────────

_EXTRACTOR_SRC = (
    Path(__file__).resolve().parent.parent
    / "services/memory/skill_extractor.py"
).read_text(encoding="utf-8")

_CHAT_HELPERS_SRC = (
    Path(__file__).resolve().parent.parent / "routes/chat_helpers.py"
).read_text(encoding="utf-8")

_AGENT_LOOP_SRC = (
    Path(__file__).resolve().parent.parent / "src/agent_loop.py"
).read_text(encoding="utf-8")

_SKILLS_ROUTES_SRC = (
    Path(__file__).resolve().parent.parent / "routes/skills_routes.py"
).read_text(encoding="utf-8")

# ── Source-text tests — gate constants ───────────────────────────────────────


def test_extractor_min_confidence_is_085():
    """MIN_CONFIDENCE must be 0.85 — aligned with the injection floor."""
    assert "MIN_CONFIDENCE = 0.85" in _EXTRACTOR_SRC


def test_extractor_gate_is_and_with_tool_floor_three():
    """Extraction gate in skill_extractor.py uses AND with tool floor >= 3."""
    assert "round_count < 2 or tool_count < 3" in _EXTRACTOR_SRC


def test_chat_helpers_outer_gate_is_and_with_tool_floor_three():
    """Outer extraction gate in chat_helpers.py uses AND with tool floor >= 3."""
    assert "agent_rounds >= 2 and agent_tool_calls >= 3" in _CHAT_HELPERS_SRC


def test_injection_path_auto_approve_default_is_false():
    """agent_loop.py injection path must default auto_approve_skills to False."""
    assert 'auto_approve_skills", False)' in _AGENT_LOOP_SRC


def test_audit_finalization_auto_approve_default_is_false():
    """skills_routes.py audit-finalization path must default auto_approve_skills to False."""
    assert 'auto_approve_skills", False)' in _SKILLS_ROUTES_SRC


# ── Behavioural test helpers ──────────────────────────────────────────────────

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


# ── Behavioural tests — gate thresholds ──────────────────────────────────────


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
    monkeypatch.setattr(
        "routes.prefs_routes._load_for_user",
        lambda owner: {},
    )

    entry, sm = await _call_extractor(monkeypatch, _GOOD_RESPONSE, round_count=2, tool_count=3)
    assert entry is not None
    assert sm.added[0].get("status") == "draft"
