"""
Verify that the mandatory consultation and unconditional-authority language has
been removed from the skill-related sections of src/agent_loop.py, and that
the replacement advisory language is in place.

fix(agent): reframe skill prompts as advisory — remove mandatory consultation
and unconditional authority language (jdmanring/odysseus#85)

Test strategy: static source-text assertions.  The agent prompt strings are
literal constants in agent_loop.py — a source-level check is direct and does
not require spinning up the agent.  Presence checks guard against a future
edit accidentally removing the replacement text; absence checks guard against
the bad strings being re-introduced.
"""
from pathlib import Path

_SRC = (Path(__file__).resolve().parent.parent / "src" / "agent_loop.py").read_text(encoding="utf-8")

# ── Absence assertions — bad language removed ─────────────────────────────────


def test_manage_skills_no_before_doing_domain_work():
    """manage_skills tool description must not mandate pre-task lookup."""
    assert "BEFORE doing domain work" not in _SRC


def test_manage_skills_no_authoritative_guidance_in_tool_desc():
    """manage_skills tool description must not call draft skills authoritative."""
    # Anchor on the unique content of the tool description entry, not the first
    # occurrence of "manage_skills" which appears earlier in set literals.
    anchor = '"- ```manage_skills```'
    idx = _SRC.index(anchor)
    tool_desc = _SRC[idx:idx + 800]
    assert "authoritative guidance" not in tool_desc


def test_matched_skills_no_proven_to_work():
    """Matched-skills header must not claim skills are proven to work."""
    assert "proven to work" not in _SRC


def test_matched_skills_no_follow_step_by_step():
    """Matched-skills header must not unconditionally mandate step-by-step execution."""
    assert "Follow them step by step" not in _SRC


def test_skill_index_no_consult_before_domain_work():
    """Skill index header must not instruct pre-task mandatory consultation."""
    assert "consult before doing domain work" not in _SRC


def test_skill_index_no_treat_as_authoritative():
    """Skill index header must not instruct agent to treat skills as authoritative."""
    assert "treat them as authoritative" not in _SRC


# ── Presence assertions — advisory replacement language is in place ───────────


def test_manage_skills_tool_desc_is_conditional():
    """manage_skills description must frame lookup as conditional on domain relevance."""
    assert "check the skill registry — there may be a reusable procedure" in _SRC


def test_manage_skills_tool_desc_distinguishes_published_from_draft():
    """manage_skills description must label published skills as user-reviewed."""
    assert "Published skills are user-reviewed; drafts are candidate procedures from prior sessions" in _SRC


def test_matched_skills_header_uses_candidate_language():
    """Matched-skills header must frame skills as candidate procedures, not proven facts."""
    assert "candidate procedures" in _SRC


def test_matched_skills_header_preserves_judgment_clause():
    """Matched-skills header must tell the agent to use its own judgment on weak matches."""
    assert "use your own judgment" in _SRC


def test_skill_index_header_uses_reference_framing():
    """Skill index header must frame skills as reference procedures, not pre-task mandates."""
    assert "Reference procedures for this session" in _SRC


def test_skill_index_header_says_evaluate_before_following():
    """Skill index header must tell the agent to evaluate drafts before following."""
    assert "evaluate fit before following" in _SRC
