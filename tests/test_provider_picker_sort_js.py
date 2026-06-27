"""Guard: the Add API Models provider picker renders alphabetically.

The picker order used to come from the raw static <option> order, which drifted out
of A-Z as providers were appended. _renderPickerMenu must sort at render time so it
cannot drift again. Static assertion on static/js/admin.js.
"""
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "static" / "js" / "admin.js"


def _picker_block() -> str:
    src = _SRC.read_text(encoding="utf-8")
    start = src.index("function _renderPickerMenu(")
    return src[start: src.index("pickerMenu.innerHTML", start) + 200]


def test_picker_sorts_by_label():
    block = _picker_block()
    assert "localeCompare" in block, "provider picker must sort options at render time"
    assert "sensitivity: 'base'" in block, "sort should be case-insensitive"


def test_picker_pins_custom_first():
    # The blank-value 'Custom URL' option must stay first, not sort into the C's.
    block = _picker_block()
    assert "filter(o => !o.value)" in block
