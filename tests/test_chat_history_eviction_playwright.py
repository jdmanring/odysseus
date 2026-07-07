"""Behavioural seam test for chat-history DOM eviction (sessions.js).

The eviction pass in `_installHistoryPager` bounds a paged session's DOM by
trimming the oldest off-screen message nodes and rewinding the pager's offset,
so the paginated history endpoint refetches exactly what was evicted on
scroll-up. This test proves the load-bearing invariant in real Chromium against
the real server: after eviction + refetch there is **no duplicate and no gap at
the seam**, and the node count stays bounded.

It boots the actual app against a throwaway SQLite DB seeded with one long
session, then drives the real sessions.js scroll handler — no mocked DOM, no
copied logic. It also exercises the paginated /api/history endpoint end to end
(which only works once the shadowing legacy route is removed).

The seed interleaves filtered-null rows ("Continue where you left off" renders
to null), so DB row offsets diverge from the visible sequence. This is the case
that distinguishes the offset-tagging design from a node/primary-count design: a
counting rewind would misalign at these gaps and produce a duplicate or gap on
refetch. Multi-node messages (an .agent-thread primary with trailing tool nodes)
are handled structurally — eviction counts *primaries* via the selector, not raw
nodes — so the overshoot-duplicate mode cannot arise; this test does not seed one.

Scope: this validates correctness (no gap/duplicate) and a bounded live node
count. It does NOT measure RSS — bounding live nodes aids responsiveness and
memory in standard browsers, but note that in QtWebEngine an evicted node becomes
a detached node that Oilpan won't reclaim without an explicit gc()/pressure
signal, so this is not by itself a QtWebEngine OOM fix.

Run:
    venv/bin/python -m pytest tests/test_chat_history_eviction_playwright.py -v
"""
import os
import shutil
import signal
import socket
import subprocess
import time
import urllib.request

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The cap enforced in static/js/sessions.js (MAX_LIVE_HISTORY_NODES). Kept in
# sync manually; the test seeds comfortably more than this so eviction fires.
CAP = 240
N_MESSAGES = 420   # ~6/7 renderable after filtered-null markers -> comfortably > CAP


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _seed_session(db_url, session_id, n):
    """Insert one session + n ordered messages straight into the file DB.

    conftest imports core.database with an in-memory URL at collection, so its
    module-level engine is the wrong one. Bind a fresh engine to the server's
    file DB and seed through that.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from core.database import Base, Session as DbSession, ChatMessage as DbChatMessage
    from datetime import datetime, timedelta
    import uuid

    engine = create_engine(db_url)
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    try:
        db.query(DbChatMessage).filter(DbChatMessage.session_id == session_id).delete()
        db.query(DbSession).filter(DbSession.id == session_id).delete()
        db.add(DbSession(
            id=session_id, name="Eviction Seam", endpoint_url="http://localhost/v1",
            model="test-model", owner=None,
        ))
        # Every 7th DB row is a filtered-null marker ("Continue where you left
        # off" renders to null via _renderHistoryMessage), so the DB row offset
        # deliberately DIVERGES from the visible sequence. Only renderable rows
        # get a SEQMSG number, and they must stay contiguous in render order
        # across eviction+refetch — precisely the offset-tagging invariant that
        # a counting-based eviction would break at these gaps.
        base_t = datetime(2026, 1, 1, 0, 0, 0)
        seq = 0
        for i in range(n):
            if i % 7 == 3:
                content = "Continue where you left off"   # -> renders to null
                role = "user"
            else:
                content = f"SEQMSG {seq:04d}"
                role = "user" if seq % 2 == 0 else "assistant"
                seq += 1
            db.add(DbChatMessage(
                id=str(uuid.uuid4()),
                session_id=session_id,
                role=role,
                content=content,
                timestamp=base_t + timedelta(seconds=i),
            ))
        db.commit()
    finally:
        db.close()


@pytest.fixture(scope="module")
def live_server(tmp_path_factory):
    pytest.importorskip("playwright.sync_api")
    datadir = str(tmp_path_factory.mktemp("evict_data"))
    db_url = f"sqlite:///{datadir}/app.db"

    session_id = "evict-seam-session"
    _seed_session(db_url, session_id, N_MESSAGES)

    port = _free_port()
    env = dict(os.environ)
    env.update({
        "ODYSSEUS_DATA_DIR": datadir,
        "DATABASE_URL": db_url,
        "AUTH_ENABLED": "false",
        "LOCALHOST_BYPASS": "true",
        "APP_PORT": str(port),
    })
    launcher = (
        "import uvicorn, app; "
        f"uvicorn.run(app.app, host='127.0.0.1', port={port}, log_level='warning')"
    )
    srv = subprocess.Popen(
        [f"{REPO}/venv/bin/python", "-c", launcher],
        cwd=REPO, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
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
        yield base, session_id
    finally:
        srv.send_signal(signal.SIGTERM)
        try:
            srv.wait(timeout=10)
        except Exception:
            srv.kill()
        shutil.rmtree(datadir, ignore_errors=True)


_SEQ_JS = r"""
() => {
  const box = document.getElementById('chat-history');
  const sel = '.msg, .agent-thread, .gallery-bubble';
  const nums = [];
  box.querySelectorAll(sel).forEach(el => {
    const m = (el.textContent || '').match(/SEQMSG (\d+)/);
    if (m) nums.push(parseInt(m[1], 10));
  });
  return { count: box.querySelectorAll(sel).length, nums };
}
"""

_SCROLL_TOP = "() => { const b=document.getElementById('chat-history'); b.scrollTop=0; b.dispatchEvent(new Event('scroll')); }"
_SCROLL_BOTTOM = "() => { const b=document.getElementById('chat-history'); b.scrollTop=b.scrollHeight; b.dispatchEvent(new Event('scroll')); }"


def _assert_contiguous(nums, label):
    assert nums, f"{label}: no messages rendered"
    for a, b in zip(nums, nums[1:]):
        assert b != a, f"{label}: DUPLICATE at {a}"
        assert b == a + 1, f"{label}: GAP/DISORDER {a} -> {b}"


def _page_up_until(page, predicate, tries=60):
    for _ in range(tries):
        state = page.evaluate(_SEQ_JS)
        if predicate(state):
            return state
        page.evaluate(_SCROLL_TOP)
        page.wait_for_timeout(250)
    return page.evaluate(_SEQ_JS)


def test_backend_paginates_history(live_server):
    """The paginated /api/history endpoint must actually paginate — regression
    guard for the legacy-route shadowing that made it return the full history."""
    base, session_id = live_server
    import json
    r = urllib.request.urlopen(base + f"/api/history/{session_id}?limit=24", timeout=10)
    data = json.loads(r.read())
    assert len(data.get("history", [])) == 24, "endpoint did not honour ?limit"
    assert data.get("total") == N_MESSAGES
    assert data.get("has_more_before") is True


def test_eviction_seam_no_gap_no_duplicate(live_server):
    from playwright.sync_api import sync_playwright

    base, session_id = live_server
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_context(viewport={"width": 1100, "height": 800}).new_page()
        try:
            page.goto(base + "/", wait_until="networkidle", timeout=30000)
            page.wait_for_selector("#chat-history", timeout=15000)

            page.evaluate(
                """async (sid) => {
                    await window.sessionModule.loadSessions();
                    await window.sessionModule.selectSession(sid);
                }""",
                session_id,
            )
            page.wait_for_function(
                "() => document.querySelectorAll('#chat-history .msg, #chat-history .agent-thread').length > 0",
                timeout=15000,
            )

            # Initial load is one page (paginated) — well under the cap.
            initial = page.evaluate(_SEQ_JS)
            assert initial["count"] < CAP, f"initial load not paginated: {initial['count']}"

            # 1) Page in older history past the cap; paging stays contiguous.
            grown = _page_up_until(page, lambda s: s["count"] > CAP)
            assert grown["count"] > CAP, f"could not grow past cap: {grown['count']}"
            _assert_contiguous(grown["nums"], "after paging")
            oldest_before = grown["nums"][0]

            # 2) Scroll down -> eviction trims the oldest off-screen nodes.
            page.evaluate(_SCROLL_BOTTOM)
            page.wait_for_timeout(300)
            after_evict = page.evaluate(_SEQ_JS)
            assert after_evict["count"] <= CAP, f"eviction did not bound DOM: {after_evict['count']}"
            _assert_contiguous(after_evict["nums"], "after eviction")
            assert after_evict["nums"][0] > oldest_before, "nothing evicted from the top"

            # 3) Scroll back up -> pager refetches the evicted rows; seam clean.
            refetched = _page_up_until(page, lambda s: s["nums"] and s["nums"][0] < after_evict["nums"][0])
            _assert_contiguous(refetched["nums"], "after refetch")
            assert refetched["nums"][0] < after_evict["nums"][0], "refetch did not restore evicted rows"
        finally:
            browser.close()
