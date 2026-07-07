"""Static validation of chatHistory.js + sessions.js server-paged history.

The virtualization holds only the pages fetched so far in `_all`. Upstream's
history endpoint caps a page at 100 messages, so without on-demand paging a long
chat would only ever expose its most recent 100 messages (the merge regression
this guards against). These checks lock in the contract that scroll-up pulls
older pages from the backend and feeds them into the virtualization.

chatHistory.js / sessions.js are browser-coupled and cannot be imported in
pytest, so — like the sibling *_js.py tests — this analyses the source text.

Manual verification (done before merge):
  1. Open a session with >100 messages; only the last ~50 render.
  2. Scroll to the top repeatedly — older pages load from the server, past 100.
  3. Scroll position does not jump; DOM child count stays bounded.
"""

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_CH = (_ROOT / "static" / "js" / "chatHistory.js").read_text(encoding="utf-8")
_SESS = (_ROOT / "static" / "js" / "sessions.js").read_text(encoding="utf-8")


# --- chatHistory.js: the pager machinery -----------------------------------

def test_server_page_constant_matches_backend_cap():
    assert re.search(r"var\s+SERVER_PAGE\s*=\s*100\b", _CH)


def test_fetch_older_method_exists():
    assert "MessageWindow.prototype._fetchOlderFromServer" in _CH


def test_load_accepts_paging_opts():
    assert re.search(r"MessageWindow\.prototype\.load\s*=\s*function\s*\(\s*messages\s*,\s*opts\s*\)", _CH)
    for field in ("_olderLoader", "_serverOffset", "_serverHasMore", "_sessionId"):
        assert field in _CH, field


def test_load_older_triggers_server_fetch_when_buffer_exhausted():
    # In the from>=upTo branch, it must try the server before dead-ending.
    body = _CH[_CH.index("prototype._loadOlder"):]
    branch = body[body.index("from >= upTo"):body.index("from >= upTo") + 400]
    assert "_fetchOlderFromServer()" in branch
    assert "_serverHasMore" in branch


def test_sentinel_survives_while_server_has_more():
    body = _CH[_CH.index("prototype._attachSentinel"):]
    head = body[:400]
    # Must NOT bail on _startIdx===0 alone; only when there is also nothing on the server.
    assert "_startIdx === 0 && !this._serverHasMore" in head


def test_fetch_older_guards_against_stale_session():
    body = _CH[_CH.index("prototype._fetchOlderFromServer"):]
    body = body[:body.index("return true;")]
    assert "_fetching" in body                     # single in-flight guard
    assert "gen !== self._gen" in body             # reset/session-switch guard
    assert "msgs.concat(self._all)" in body        # prepend older page
    assert "self._startIdx += msgs.length" in body # shift window indices


def test_reset_clears_paging_state():
    body = _CH[_CH.index("prototype.reset"):]
    body = body[:body.index("};")]
    for field in ("_serverOffset", "_serverHasMore", "_fetching", "_olderLoader", "_sessionId"):
        assert field in body, field


# --- sessions.js: wiring the pager --------------------------------------------

def test_shared_mapper_defined_and_reused():
    assert "function _mapHistoryMessages(" in _SESS
    # Used by both the initial render and the scroll-up loader.
    assert len(re.findall(r"_mapHistoryMessages\(", _SESS)) >= 3  # def + 2 call sites


def test_initial_fetch_is_a_page_not_a_bogus_400():
    assert "limit=400" not in _SESS
    assert re.search(r"_historyUrl\(id,\s*\{\s*limit:\s*100\s*\}\)", _SESS)


def test_load_call_passes_older_loader():
    call = _SESS[_SESS.index("window.chatHistory.load(_preparedMsgs"):]
    call = call[:600]
    for key in ("sessionId", "serverOffset", "serverHasMore", "olderLoader"):
        assert key in call, key
    assert "has_more_before" in call


def test_older_loader_fetches_by_offset_and_maps():
    call = _SESS[_SESS.index("olderLoader:"):]
    call = call[:500]
    assert "_historyUrl(sid, { limit, offset })" in call
    assert "_mapHistoryMessages(" in call
    assert "has_more_before" in call
