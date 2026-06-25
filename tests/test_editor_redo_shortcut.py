"""Guard for the Ctrl+Shift+Z (redo) keyboard shortcut (jdmanring#100).

With Shift held, e.key for the Z key is the uppercase 'Z', so a lowercase-only
check silently disables redo. The undo/redo chord must accept both cases.
"""
from pathlib import Path

_SRC = (Path(__file__).resolve().parents[1] / "static/js/editor/keyboard-shortcuts.js").read_text(encoding="utf-8")


def test_undo_redo_chord_accepts_uppercase_z():
    # The chord that dispatches undo()/redo() must match both 'z' and 'Z' so
    # Ctrl+Shift+Z (which delivers e.key === 'Z') reaches the redo() branch.
    assert "e.key === 'z' || e.key === 'Z'" in _SRC


def test_redo_still_gated_on_shift():
    # Same chord: shiftKey selects redo, otherwise undo.
    idx = _SRC.index("e.key === 'z' || e.key === 'Z'")
    line = _SRC[idx:idx + 120]
    assert "if (e.shiftKey) redo(); else undo();" in line
