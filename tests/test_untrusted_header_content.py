"""Regression tests for UNTRUSTED_CONTEXT_HEADER content.

The header must:
  - Scope its restriction to the guarded block ("inside this block itself")
  - Reassert that user and system-prompt instructions remain authoritative
  - NOT contain broad "Do not call tools" language that bleeds into user turns

These tests protect against the regression introduced by upstream #1629 where
the header's restriction was unscoped, causing the model to refuse user requests
citing untrusted-source policy.
"""

from src.prompt_security import UNTRUSTED_CONTEXT_HEADER


def test_header_reasserts_user_instruction_authority():
    """Header must explicitly state that user/system-prompt instructions remain in effect."""
    assert "remain in full effect" in UNTRUSTED_CONTEXT_HEADER


def test_header_restriction_is_scoped_to_block():
    """Restriction must be scoped to 'inside this block' — not applied globally."""
    assert "inside this block" in UNTRUSTED_CONTEXT_HEADER


def test_header_does_not_globally_ban_tool_calls():
    """Header must not contain unscoped 'Do not call tools' that bleeds past the block."""
    assert "Do not call tools" not in UNTRUSTED_CONTEXT_HEADER
    assert "do not call tools" not in UNTRUSTED_CONTEXT_HEADER


def test_header_identifies_content_as_reference_material():
    """Header must direct model to treat content as reference, not instructions."""
    assert "reference material" in UNTRUSTED_CONTEXT_HEADER


def test_header_names_external_data_sources():
    """Header must identify what kinds of content are untrusted so scope is clear."""
    header = UNTRUSTED_CONTEXT_HEADER
    assert any(term in header for term in ("file read", "shell output", "web fetch"))
