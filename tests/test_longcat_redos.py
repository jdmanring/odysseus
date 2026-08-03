"""LongCat tool-call scanning must stay linear on attacker-shaped input.

Model output is untrusted. A lazy `<open>([\\s\\S]*?)</close>` driven by finditer
retries from every opener and rescans to end-of-string, which is O(n^2) on "many
openers, no closer" — CodeQL flags it as py/polynomial-redos, and upstream
eliminated exactly this shape across tool_parsing.py in #4704/#4877/#4941/#4943.

Measured on the pre-fix pattern: 200/400/800/1600/3200 openers ->
4.0/15.8/63.3/244.0/947.7 ms. After the rework: 0.036/0.067/0.136/0.245/0.489 ms.

The timing assertion is deliberately loose (a CI box is not a benchmark rig). It
only needs to separate linear from quadratic, and at 3200 openers those differ by
three orders of magnitude.
"""
import os
import time

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import src.agent_tools  # noqa: F401  — resolve the package (circular import)
from src.tool_parsing import (  # noqa: E402
    _LONGCAT_OPEN_RE,
    _LONGCAT_CLOSE_RE,
    _iter_delimited,
)


def _scan(text):
    return list(_iter_delimited(text, _LONGCAT_OPEN_RE, _LONGCAT_CLOSE_RE))


def test_opener_flood_stays_linear():
    """Many openers, no closer — the attack shape. Must not blow up."""
    small = "<longcat_tool_call>" * 400
    large = "<longcat_tool_call>" * 3200          # 8x the input

    t0 = time.perf_counter(); _scan(small); small_ms = (time.perf_counter() - t0) * 1000
    t0 = time.perf_counter(); _scan(large); large_ms = (time.perf_counter() - t0) * 1000

    # Quadratic would be ~64x for 8x input; linear ~8x. Allow generous headroom
    # for a loaded CI box and still fail a quadratic scan by a wide margin.
    assert large_ms < 200, f"3200-opener flood took {large_ms:.1f}ms — scan is not linear"
    if small_ms > 0.01:
        assert large_ms / small_ms < 25, (
            f"growth {large_ms / small_ms:.1f}x for 8x input looks quadratic "
            f"({small_ms:.3f}ms -> {large_ms:.3f}ms)"
        )


def test_stale_closer_before_opener_flood():
    """A closer BEFORE the openers must not re-enable the rescan.

    A whole-string 'is a closer present?' guard would pass here and every opener
    would still rescan; pairing each opener only with a closer AFTER it is what
    actually closes the hole.
    """
    text = "</longcat_tool_call>" + "<longcat_tool_call>" * 2000
    t0 = time.perf_counter(); _scan(text); ms = (time.perf_counter() - t0) * 1000
    assert ms < 100, f"stale-closer flood took {ms:.1f}ms"


def test_valid_blocks_still_parse():
    """The hardening must not change behaviour on well-formed input."""
    text = (
        '<longcat_tool_call>{"name":"a","arguments":{}}</longcat_tool_call>'
        "some prose in between"
        '<longcat_tool_call>{"name":"b","arguments":{}}</longcat_tool_call>'
    )
    bodies = [text[i0:i1] for _s, i0, i1, _e in _scan(text)]
    assert bodies == ['{"name":"a","arguments":{}}', '{"name":"b","arguments":{}}']


def test_unclosed_trailing_block_is_ignored():
    text = ('<longcat_tool_call>{"name":"a","arguments":{}}</longcat_tool_call>'
            '<longcat_tool_call>{"name":"never closed"')
    assert len(_scan(text)) == 1
