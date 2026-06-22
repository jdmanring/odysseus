"""Static-analysis tests for squashOutsideCode fast path in markdown.js."""
from pathlib import Path

_SRC = (Path(__file__).resolve().parent.parent / "static/js/markdown.js").read_text(encoding="utf-8")


def _squash_block() -> str:
    start = _SRC.index("export function squashOutsideCode(")
    end = _SRC.index("\nexport function renderContent(", start)
    return _SRC[start:end]


def test_squash_fast_path_on_no_backticks():
    """squashOutsideCode short-circuits before any allocation when no backticks present."""
    assert "includes('```')" in _squash_block()


def test_squash_fast_path_precedes_split():
    """Fast-path guard must appear before the split() call."""
    block = _squash_block()
    assert block.index("includes('```')") < block.index("split(")


def test_squash_code_fence_path_preserved():
    """Code-fence path (split + join) still present for responses with backticks."""
    block = _squash_block()
    assert "split" in block and "join('```')" in block
