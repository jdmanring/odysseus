"""
Verify that the mandatory consultation and unconditional-authority language has
been removed from the skill-related sections of src/agent_loop.py.

fix(agent): reframe skill prompts as advisory — remove mandatory consultation
and unconditional authority language (jdmanring/odysseus#85)
"""
from pathlib import Path

_SRC = (Path(__file__).resolve().parent.parent / "src" / "agent_loop.py").read_text(encoding="utf-8")


def test_manage_skills_no_before_doing_domain_work():
    """manage_skills tool description must not mandate pre-task lookup."""
    assert "BEFORE doing domain work" not in _SRC


def test_manage_skills_no_authoritative_guidance_in_tool_desc():
    """manage_skills tool description must not call draft skills authoritative."""
    idx = _SRC.index('"manage_skills"')
    tool_desc = _SRC[idx:idx + 600]
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
