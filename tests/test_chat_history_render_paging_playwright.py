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
import signal
import socket
import subprocess
import time
import urllib.request
import uuid
from datetime import datetime, timedelta

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
N_MESSAGES = 300
SID = "render-paging-check"


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _seed(db_url):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from core.database import Base, Session as DbSession, ChatMessage as DbChatMessage

    engine = create_engine(db_url)
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    try:
        db.add(DbSession(id=SID, name="Render Paging", endpoint_url="http://localhost/v1",
                         model="test-model", owner=None))
        t = datetime(2026, 1, 1)
        for i in range(N_MESSAGES):
            db.add(DbChatMessage(id=str(uuid.uuid4()), session_id=SID,
                                 role="user" if i % 2 == 0 else "assistant",
                                 content=f"SEQMSG {i:04d}", timestamp=t + timedelta(seconds=i)))
        db.commit()
    finally:
        db.close()


@pytest.fixture(scope="module")
def live_server(tmp_path_factory):
    pytest.importorskip("playwright.sync_api")
    datadir = str(tmp_path_factory.mktemp("render_paging"))
    db_url = f"sqlite:///{datadir}/app.db"
    _seed(db_url)
    port = _free_port()
    env = dict(os.environ)
    env.update({"ODYSSEUS_DATA_DIR": datadir, "DATABASE_URL": db_url,
                "AUTH_ENABLED": "false", "LOCALHOST_BYPASS": "true", "APP_PORT": str(port)})
    srv = subprocess.Popen(
        [f"{REPO}/venv/bin/python", "-c",
         f"import uvicorn, app; uvicorn.run(app.app, host='127.0.0.1', port={port}, log_level='warning')"],
        cwd=REPO, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(base + "/", timeout=2)
                break
            except Exception:
                time.sleep(0.5)
        else:
            srv.kill()
            pytest.fail("server did not start")
        yield base
    finally:
        srv.send_signal(signal.SIGTERM)
        try:
            srv.wait(timeout=10)
        except Exception:
            srv.kill()
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
