"""Static guard: modal z-promote re-entry guard reads the inline style first.

ui.js's _promote MutationObserver guard must read the element's INLINE
style.zIndex before falling back to getComputedStyle. Reading only the
computed value loops to renderer OOM when an OS reduce-motion setting is
on: the global reduce-motion CSS turns z-index writes into 10 microsecond
transitions (transition-property defaults to `all`), transitions outrank
inline !important in the cascade, and MutationObserver storms run as
microtasks during which document time is frozen — so the computed value
never reaches the written one and the observer never stops.
"""
from pathlib import Path

UI = (
    Path(__file__).resolve().parent.parent / "static" / "js" / "ui.js"
).read_text(encoding="utf-8")


def test_zpromote_guard_reads_inline_style_first():
    line = next((l for l in UI.splitlines() if "const cur = parseInt(" in l), "")
    assert "m.style.zIndex" in line, "guard must read the inline write first"
    inline = line.index("m.style.zIndex")
    computed = line.index("getComputedStyle(m).zIndex")
    assert inline < computed, (
        "inline style must be consulted before the computed value — the "
        "computed z-index can be pinned mid-transition under reduce-motion"
    )
