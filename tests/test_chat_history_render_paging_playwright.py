"""Real-browser regression test for chat-history rendering + server paging on develop.

Guards the fork's MessageWindow server-paging path end to end against the real
server — the coverage the static/mock tests lacked. It would have caught the
`markdownModule is not defined` regression (sessions.js `_mapHistoryMessages`
threw on every session load, so history rendered empty), and it exercises the
real `_fetchOlderFromServer` scroll-up paging that the mock-DOM harness cannot.

Asserts:
  1. the backend paginates (`?limit` honoured, `has_more_before` sent);
  2. selectSession actually renders message bubbles (no swallowed ReferenceError);
  3. scroll-up reaches the oldest message via server paging;
  4. the DOM never holds the entire history at once (MessageWindow stays bounded).

Run:
    venv/bin/python -m pytest tests/test_chat_history_render_paging_playwright.py -v
"""
import json
import os
import shutil
import sys
import urllib.request

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tests", "bench"))
from live_app import LiveApp, seed_session  # noqa: E402  (shared real-app bootstrap)

N_MESSAGES = 300
SID = "render-paging-check"


def _contents():
    """N_MESSAGES message bodies. The last few (in the initial render window) carry
    rich content — fenced code, markdown, an inline image — so the real
    _mapHistoryMessages → markdownModule.renderContent path is exercised on
    non-trivial shapes, not just plain strings. The SEQMSG marker is preserved so
    the paging/bounding assertions (which match /SEQMSG (\\d+)/) still hold."""
    out = []
    for i in range(N_MESSAGES):
        content = f"SEQMSG {i:04d}"
        if i == N_MESSAGES - 3:
            content += "\n\n```python\nprint('hello')\n```\n\n**bold** and `code`"
        elif i == N_MESSAGES - 2:
            content += "\n\n![tiny](data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==)"
        elif i == N_MESSAGES - 1:
            content += "\n\n- list item\n- another\n\n> a quote"
        out.append(content)
    return out


@pytest.fixture(scope="module")
def live_server(tmp_path_factory):
    pytest.importorskip("playwright.sync_api")
    datadir = str(tmp_path_factory.mktemp("render_paging"))
    try:
        srv = LiveApp(datadir, lambda db_url: seed_session(
            db_url, SID, _contents(), name="Render Paging", model="test-model"))
    except RuntimeError as e:
        pytest.fail(str(e))
    try:
        yield srv.base
    finally:
        srv.stop()
        shutil.rmtree(datadir, ignore_errors=True)


_SEQ_JS = r"""() => {
  const b = document.getElementById('chat-history');
  const els = [...b.querySelectorAll('.msg,.agent-thread,.gallery-bubble')];
  const nums = els.map(e => { const m = (e.textContent||'').match(/SEQMSG (\d+)/); return m ? +m[1] : null; }).filter(x => x !== null);
  return { count: els.length, min: nums.length ? Math.min(...nums) : null };
}"""


def test_history_renders_and_pages(live_server):
    from playwright.sync_api import sync_playwright
    base = live_server

    # 1) backend paginates
    d = json.loads(urllib.request.urlopen(base + f"/api/history/{SID}?limit=24", timeout=10).read())
    assert len(d["history"]) == 24 and d["total"] == N_MESSAGES and d["has_more_before"] is True

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_context(viewport={"width": 1100, "height": 800}).new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" and "markdownModule" in m.text else None)
        try:
            page.goto(base + "/", wait_until="networkidle", timeout=30000)
            page.wait_for_selector("#chat-history", timeout=15000)
            page.evaluate("async (sid)=>{await window.sessionModule.loadSessions(); await window.sessionModule.selectSession(sid);}", SID)

            # 2) messages actually render (regression guard for the ReferenceError)
            page.wait_for_function(
                "()=>document.querySelectorAll('#chat-history .msg,#chat-history .agent-thread').length>0",
                timeout=15000,
            )
            assert not any("markdownModule" in e for e in errors), f"render error: {errors}"

            # Rich content in the initial window rendered through the real markdown
            # path: the fenced code block became a <pre> (regression guard for the
            # markdownModule class on non-trivial content, not just plain strings).
            assert page.evaluate("document.querySelectorAll('#chat-history pre').length") > 0, \
                "fenced code block did not render — markdown render path broken for rich content"

            init = page.evaluate(_SEQ_JS)
            assert init["count"] < N_MESSAGES, f"initial load not bounded: {init['count']}"

            # 3) scroll-up reaches the oldest message; 4) DOM never holds all
            max_dom = init["count"]
            reached = init["min"] == 0
            for _ in range(80):
                st = page.evaluate(_SEQ_JS)
                max_dom = max(max_dom, st["count"])
                if st["min"] == 0:
                    reached = True
                    break
                page.evaluate("()=>{const b=document.getElementById('chat-history'); b.scrollTop=0; b.dispatchEvent(new Event('scroll'));}")
                page.wait_for_timeout(200)

            assert reached, "scroll-up did not reach the oldest message (server paging broken)"
            assert max_dom < N_MESSAGES, f"DOM held the entire history ({max_dom}) — not bounded"
        finally:
            browser.close()
