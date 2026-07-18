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

# Long session for the pinned-top walk (#130): the swallowed-fire race needs many
# server-fetch `_loading` windows to manifest; n=300 passes on broken code.
N_LONG = 2000
SID_LONG = "pinned-top-walk"


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
        def _seed(db_url):
            seed_session(db_url, SID, _contents(), name="Render Paging", model="test-model")
            seed_session(db_url, SID_LONG, [f"SEQMSG {i:04d}" for i in range(N_LONG)],
                         name="Pinned Top Walk", model="test-model")
        srv = LiveApp(datadir, _seed)
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


# Constant DOM bound during a full scroll-up walk (issue #129).
#
# The bound is a CONSTANT derived from the window geometry, not `< N`: the old
# assertion above passed while the DOM held ~280 of 300 messages, because "less
# than all of them" is trivially true one batch before the end. The real
# invariant is BIDI_MSG_CAP (80) historical messages plus one BATCH_SIZE (25)
# overshoot before the prune runs, plus slack.
_DOM_MSG_BOUND = 130


def test_scrollup_dom_stays_bounded(live_server):
    """Walk to the oldest message over real server paging; the DOM must stay at
    a constant size and the chIdx tag space must stay coherent.

    Guards issue #129: _fetchOlderFromServer prepends to _all and shifts the
    index space without retagging rendered nodes, so tags from successive pages
    collide (measured: a full 300-message walk left tags 0-99 against _endIdx
    280) and the Phase-3 prune breaks at the first stale tag, removing nothing.
    """
    from playwright.sync_api import sync_playwright
    base = live_server

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_context(viewport={"width": 900, "height": 700}).new_page()
        try:
            page.goto(base + "/", wait_until="networkidle", timeout=30000)
            page.wait_for_selector("#chat-history", timeout=15000)
            page.evaluate("async (sid)=>{await window.sessionModule.loadSessions();"
                          " await window.sessionModule.selectSession(sid);}", SID)
            page.wait_for_function(
                "()=>document.querySelectorAll('#chat-history .msg,#chat-history .agent-thread').length>0",
                timeout=15000)
            page.wait_for_timeout(300)

            # Shared driver (CSP blocks add_script_tag on the real app; evaluate()
            # rides CDP, which page CSP does not govern).
            with open(os.path.join(REPO, "tests", "bench", "scroll_driver.js")) as fh:
                page.evaluate(fh.read())
            walk = page.evaluate(
                "async () => window.scrollDriver.walkToOldest(document.getElementById('chat-history'))")
            assert walk["complete"], f"walk never reached the oldest message: {walk}"

            st = page.evaluate("""() => {
              const w = window.chatHistory, box = document.getElementById('chat-history');
              const tags = [...box.querySelectorAll('[data-ch-idx]')].map(e => +e.dataset.chIdx);
              return { taggedNodes: tags.length,
                       distinctMsgs: new Set(tags).size,
                       maxTag: tags.length ? Math.max(...tags) : null,
                       endIdx: w._endIdx, startIdx: w._startIdx };
            }""")
            # The bound: rendered historical messages, counted in MESSAGES (a
            # message may span several DOM children, so distinct tags, not nodes).
            assert st["distinctMsgs"] <= _DOM_MSG_BOUND, (
                f"DOM holds {st['distinctMsgs']} messages after the walk "
                f"(bound {_DOM_MSG_BOUND}) — scroll-up prune is not running (#129)")
            # Tag-space coherence: the bottom-most rendered message's tag must be
            # in the CURRENT _all index space. Stale tags collide across pages and
            # silently disable every chIdx consumer (prune, scroll-down reload).
            assert st["maxTag"] == st["endIdx"] - 1, (
                f"chIdx tag space is stale: max tag {st['maxTag']} vs _endIdx "
                f"{st['endIdx']} — nodes were not retagged after a server prepend")
        finally:
            browser.close()


def test_pinned_top_walk_completes(live_server):
    """Pin the viewport at the very top (scrollbar dragged to the top, or held
    Home/PgUp) and stay there; paging must still reach the oldest message.

    Guards issue #130: the top sentinel's one-shot IntersectionObserver fires on
    intersection TRANSITIONS. A fire swallowed while `_loading` is true leaves
    the re-armed observer waiting for a transition that never comes when the
    viewport stays pinned at scrollTop=0 — paging dead-ends with older messages
    still buffered ("↑ N earlier messages" shows, nothing arrives). pinnedTopWalk
    is exactly that shape; on broken code it stalls out with complete=False.

    RTT is emulated (CDP, as in tests/bench/network_arm_bench.py) because the
    swallow needs a fire to land inside the `_loading` window of a server fetch;
    at localhost RTT that window is near zero and broken code can pass by luck.
    """
    from playwright.sync_api import sync_playwright
    base = live_server

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_context(viewport={"width": 900, "height": 700}).new_page()
        try:
            page.goto(base + "/", wait_until="networkidle", timeout=30000)
            page.wait_for_selector("#chat-history", timeout=15000)
            page.evaluate("async (sid)=>{await window.sessionModule.loadSessions();"
                          " await window.sessionModule.selectSession(sid);}", SID_LONG)
            page.wait_for_function(
                "()=>document.querySelectorAll('#chat-history .msg,#chat-history .agent-thread').length>0",
                timeout=15000)
            page.wait_for_timeout(300)

            # Apply AFTER app load so only the paging fetches see the latency.
            cdp = page.context.new_cdp_session(page)
            cdp.send("Network.enable")
            cdp.send("Network.emulateNetworkConditions",
                     {"offline": False, "latency": 40,
                      "downloadThroughput": -1, "uploadThroughput": -1})

            with open(os.path.join(REPO, "tests", "bench", "scroll_driver.js")) as fh:
                page.evaluate(fh.read())
            # cadenceMs=30: re-pinning faster than a settled frame is what gets
            # fires swallowed (probe sweep 2026-07-17: 30ms cadence dead-ended at
            # RTT 40 and 400 with the issue's exact stall signature; 100/250ms
            # cadences completed). A fixed MessageWindow self-drives on batch
            # completion, so cadence must not matter.
            walk = page.evaluate(
                "async () => window.scrollDriver.pinnedTopWalk("
                "document.getElementById('chat-history'), {cadenceMs: 30})")
            st = page.evaluate("""() => {
              const w = window.chatHistory;
              return { startIdx: w._startIdx, serverHasMore: w._serverHasMore,
                       loading: w._loading, fetching: w._fetching };
            }""")
            assert walk["complete"], (
                f"pinned-top walk dead-ended: {walk} state {st} — a swallowed "
                f"sentinel-observer fire was never recovered (#130)")
            # The walk must have consumed everything: buffer and server drained.
            assert st["startIdx"] == 0 and not st["serverHasMore"], (
                f"walk 'completed' with history remaining: {st}")
        finally:
            browser.close()


def test_scrollbar_honesty_scales_with_history(live_server):
    """The container's scrollHeight must reflect the conversation, not the
    rendered window.

    Guards issue #127: load() rendered only WINDOW_SIZE messages and created no
    spacer for the unrendered range, so scrollHeight was a CONSTANT (~2.5% of a
    2000-message conversation) for any history length. With the top estimator
    spacer, reported height scales with the history: the 2000-message session
    must report several times the height of the 300-message one (truth ratio
    ~6.7; estimator-based should be close; broken code reports ~1.0). The walk
    then re-checks stability: the bar must not balloon or collapse as real
    heights replace estimates (idempotent recompute, no compounding drift).
    """
    from playwright.sync_api import sync_playwright
    base = live_server

    def _load_and_measure(page, sid):
        page.evaluate("async (sid)=>{await window.sessionModule.loadSessions();"
                      " await window.sessionModule.selectSession(sid);}", sid)
        page.wait_for_function(
            "()=>document.querySelectorAll('#chat-history .msg,#chat-history .agent-thread').length>0",
            timeout=15000)
        page.wait_for_timeout(300)
        return page.evaluate("()=>document.getElementById('chat-history').scrollHeight")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_context(viewport={"width": 900, "height": 700}).new_page()
        try:
            page.goto(base + "/", wait_until="networkidle", timeout=30000)
            page.wait_for_selector("#chat-history", timeout=15000)
            h_short = _load_and_measure(page, SID)
            h_long = _load_and_measure(page, SID_LONG)
            ratio = h_long / h_short
            assert ratio >= 4, (
                f"scrollHeight does not scale with history: n={N_LONG} reports "
                f"{h_long}px vs n={N_MESSAGES} at {h_short}px (ratio {ratio:.2f}; "
                f"truth ratio ~{N_LONG/N_MESSAGES:.1f}) — no honesty spacer (#127)")

            # Stability across a full walk: real heights replace estimates as
            # pages render and prune; the recompute is idempotent, so the bar
            # must stay in the same regime, not balloon or collapse.
            with open(os.path.join(REPO, "tests", "bench", "scroll_driver.js")) as fh:
                page.evaluate(fh.read())
            walk = page.evaluate(
                "async () => window.scrollDriver.walkToOldest(document.getElementById('chat-history'))")
            assert walk["complete"], f"walk failed: {walk}"
            h_after = page.evaluate("()=>document.getElementById('chat-history').scrollHeight")
            drift = h_after / h_long
            assert 0.5 <= drift <= 1.5, (
                f"honesty bar drifted across the walk: {h_long}px at load -> "
                f"{h_after}px at top (x{drift:.2f}) — estimator is compounding "
                f"or losing height (#126 bug class)")
        finally:
            browser.close()
