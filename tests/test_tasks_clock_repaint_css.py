"""CSS guard: the Tasks-panel clock must be isolated to its own compositor layer.

The Tasks modal is draggable (its own compositor layer); the clock updates its
textContent every second. Without isolation that repaint re-rasters the whole
modal backing texture each tick — measured ~1.7 MB/s of tiles Qt never evicts.
Promoting the clock to its own small layer + paint containment limits the
re-raster to the clock box. Issue #110.
"""
from pathlib import Path

_CSS = (Path(__file__).resolve().parents[1] / "static/style.css").read_text(encoding="utf-8")


def test_tasks_clock_isolated_to_own_layer():
    idx = _CSS.find(".tasks-clock {")
    assert idx >= 0
    block = _CSS[idx: _CSS.find("}", idx) + 1]
    assert ("translateZ(0)" in block or "translate3d(0, 0, 0)" in block
            or "will-change: transform" in block), (
        ".tasks-clock must be promoted to its own compositor layer so its 1/sec "
        "repaint does not re-raster the whole draggable modal layer"
    )
    assert "contain:" in block, ".tasks-clock must contain its paint to bound the re-raster"
