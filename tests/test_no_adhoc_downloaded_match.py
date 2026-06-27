"""Guard: the 'is this model downloaded?' decision has exactly one implementation.

This bug regressed at least three times because the decision was reimplemented inline
at every render site (the downloaded dot, the card greying, the serve gate, the row
re-mark) with divergent rules. The fix consolidated them into
static/js/model/downloaded.js (isModelDownloaded). This test fails if anyone
reintroduces a raw inline matcher against the downloaded-id set, so a new divergent
copy cannot silently come back.

Allowed uses of _cachedModelIds: building it (new Set(...)), null/size guards, and
listing it (Array.from). NOT allowed: the membership-match patterns `.has(` and
`].some(`, which are the decision this consolidation owns.
"""
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_FILES = [
    "static/js/cookbook-hwfit.js",
    "static/js/cookbook.js",
    "static/js/cookbook-diagnosis.js",
]
_FORBIDDEN = ["_cachedModelIds.has(", "_cachedModelIds].some("]


@pytest.mark.parametrize("rel", _FILES)
def test_no_inline_downloaded_match(rel):
    src = (_REPO / rel).read_text(encoding="utf-8")
    hits = [(pat, src.count(pat)) for pat in _FORBIDDEN if pat in src]
    assert not hits, (
        f"{rel} reintroduced an inline downloaded-match {hits}. Use "
        f"isModelDownloaded(model, _cachedModelIds) from static/js/model/downloaded.js "
        f"instead; that single predicate is what stops this from regressing again."
    )


def test_canonical_predicate_exists_and_is_imported():
    mod = (_REPO / "static/js/model/downloaded.js").read_text(encoding="utf-8")
    assert "export function isModelDownloaded(" in mod
    hwfit = (_REPO / "static/js/cookbook-hwfit.js").read_text(encoding="utf-8")
    assert "from './model/downloaded.js'" in hwfit
    assert "isModelDownloaded(" in hwfit
