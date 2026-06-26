"""_sigCache signature data-URL cache is bounded (#119, audit D3).

The cache stored base64 data URLs with no cap. It now has an LRU helper
(_sigCacheSet) with a max size + evict-oldest, and every write goes through it.
Static assertions on source.
"""
import re
from pathlib import Path

_DOC = (Path(__file__).resolve().parents[1] / "static" / "js" / "document.js").read_text(encoding="utf-8")


def test_helper_defines_cap_and_eviction():
    assert "_SIG_CACHE_MAX" in _DOC
    assert "function _sigCacheSet" in _DOC
    block = _DOC[_DOC.index("function _sigCacheSet"):][:300]
    assert "_sigCache.size > _SIG_CACHE_MAX" in block
    assert "_sigCache.delete(_sigCache.keys().next().value)" in block  # evict oldest


def test_all_writes_go_through_bounded_helper():
    # The only raw `_sigCache.set(` left is inside the helper itself.
    raw = re.findall(r"_sigCache\.set\(", _DOC)
    assert len(raw) == 1, f"expected 1 raw _sigCache.set (in helper), found {len(raw)}"
    # And the call sites use the helper.
    assert _DOC.count("_sigCacheSet(") >= 4
