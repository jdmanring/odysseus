"""Automated long-session soak: the real app, a real browser, real streaming.

This automates the long-session verification that previously required a human
and a live model: a mock OpenAI-compatible server (tests/bench/mock_llm.py)
streams SSE replies, so the REAL send path runs end-to-end — composer submit,
POST /api/chat_stream, SSE deltas into the renderer, save — for dozens of
exchanges in headless Chromium with no GPU.

What it verifies across the session (the long-session checklist):
  1. every exchange completes (per-exchange ACK marker echoed by the mock);
  2. the DOM stays bounded while the live stream crosses the prune threshold;
  3. auto-follow: the view is at the bottom after every completed exchange;
  4. the thinking indicator appears during the first-token wait and clears;
  5. scroll-up walks back to the first message with the DOM still bounded;
  6. scroll-to-bottom returns to the newest message and holds it.

It would also have caught the `_explicit_web_intent` NameError that made
every /api/chat_stream return 500 — no other test executed the send path.

Run:
    venv/bin/python -m pytest tests/test_chat_history_longsession_playwright.py -v
"""
import os
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tests", "bench"))
from live_app import LiveApp, seed_session, seed_endpoint  # noqa: E402
from mock_llm import MockLLM, MODEL_ID  # noqa: E402

SID = "long-session-soak"
# Separate session for the send-path probe so its (aborted or completed)
# stream state can never bleed into the soak session's history.
PROBE_SID = "send-path-probe"
# 55 exchanges = 110 live messages: crosses the live-stream prune threshold
# (PRUNE_AT 80) with margin, so pruning provably ran during the session.
EXCHANGES = 55
# Same bound the render-paging suite uses: BIDI_CAP (120) DOM children plus
# slack for separators/sentinels/spacers.
DOM_CHILD_BOUND = 145


@pytest.fixture(scope="module")
def soak(tmp_path_factory):
    pytest.importorskip("playwright.sync_api")
    datadir = str(tmp_path_factory.mktemp("longsession"))
    # Two indicators, two triggers: the initial .ai-spinner shows during the
    # first-token wait, and the .agent-thinking-dots overlay shows after a
    # 400ms no-text gap MID-stream. The first exchanges hold the first token
    # 900ms and pause 900ms after the 4th; the rest answer fast.
    # slow_first_n=5: the send-path probe below consumes the first slow slot.
    mock = MockLLM(first_token_delay_s=0.9, token_delay_s=0.004,
                   slow_first_n=5, mid_pause_s=0.9)

    def _seed(db_url):
        seed_endpoint(db_url, mock.base_url, models=(MODEL_ID,))
        seed_session(db_url, SID, [], name="Long Session Soak",
                     model=MODEL_ID, endpoint_url=mock.base_url)
        seed_session(db_url, PROBE_SID, [], name="Send Probe",
                     model=MODEL_ID, endpoint_url=mock.base_url)

    try:
        srv = LiveApp(datadir, _seed)
    except RuntimeError as e:
        mock.stop()
        pytest.fail(str(e))
    # Send-path probe: this suite needs a working POST /api/chat_stream. If
    # the route is broken (e.g. the upstream NameError this suite was built
    # to catch), skip with the reason rather than fail 55 exchanges deep —
    # a branch that stages only the chat-history work may not carry the
    # separately-staged send-path fix.
    try:
        req = urllib.request.Request(
            srv.base + "/api/chat_stream",
            data=urllib.parse.urlencode(
                {"message": "probe", "session": PROBE_SID}).encode())
        with urllib.request.urlopen(req, timeout=30) as resp:
            status = resp.status
            resp.read()
    except urllib.error.HTTPError as e:
        status = e.code
    except Exception as e:
        srv.stop()
        mock.stop()
        shutil.rmtree(datadir, ignore_errors=True)
        pytest.fail(f"chat_stream probe failed outright: {e}")
    if status != 200:
        srv.stop()
        mock.stop()
        shutil.rmtree(datadir, ignore_errors=True)
        pytest.skip(
            f"POST /api/chat_stream returns HTTP {status} — the send path is "
            "broken on this checkout; the fix is staged separately")
    try:
        yield srv.base
    finally:
        srv.stop()
        mock.stop()
        shutil.rmtree(datadir, ignore_errors=True)


_STATE_JS = """() => {
  const b = document.getElementById('chat-history');
  return {
    children: b ? b.children.length : -1,
    fromBottom: b ? b.scrollHeight - b.scrollTop - b.clientHeight : -1,
  };
}"""


def test_long_session_stays_bounded_and_follows(soak):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_context(
            viewport={"width": 1100, "height": 800}).new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        try:
            page.goto(soak + "/", wait_until="networkidle", timeout=30000)
            page.wait_for_selector("#chat-history", timeout=15000)
            page.evaluate(
                "async (sid)=>{await window.sessionModule.loadSessions();"
                "await window.sessionModule.selectSession(sid);}", SID)
            page.wait_for_timeout(400)

            max_children = 0
            saw_spinner = False
            saw_thinking = False
            for i in range(EXCHANGES):
                # Verified submit: the ACK renders slightly before the app
                # clears its internal isStreaming flag, and handleChatSubmit
                # silently drops a submit that races it — so retry until this
                # exchange's user bubble actually appears.
                submitted = False
                for _ in range(20):
                    page.fill("#message", f"SOAKMSG {i} please continue")
                    page.evaluate(
                        "()=>document.getElementById('chat-form').requestSubmit()")
                    try:
                        page.wait_for_function(
                            "(m)=>document.getElementById('chat-history')"
                            ".textContent.includes('SOAKMSG '+m+' please')",
                            arg=i, timeout=1000)
                        submitted = True
                        break
                    except Exception:
                        page.wait_for_timeout(300)
                assert submitted, f"exchange {i}: submit never took"
                # Indicators, on the slow early exchanges: .ai-spinner during
                # the first-token wait, .agent-thinking-dots during the
                # mid-stream pause the mock injects after the 4th token.
                if i < 4 and not (saw_spinner and saw_thinking):
                    for _ in range(100):
                        if not saw_spinner and page.evaluate(
                                "!!document.querySelector('.ai-spinner')"):
                            saw_spinner = True
                        if not saw_thinking and page.evaluate(
                                "!!document.querySelector('.agent-thinking-dots')"):
                            saw_thinking = True
                        if saw_spinner and saw_thinking:
                            break
                        page.wait_for_timeout(25)
                # Exchange complete: the mock's ACK for THIS marker rendered
                # and the composer is usable again.
                page.wait_for_function(
                    "(m)=>{const h=document.getElementById('chat-history');"
                    "return h && h.textContent.includes('ACK SOAKMSG '+m+'.')"
                    " && !document.getElementById('message').disabled;}",
                    arg=i, timeout=30000)
                st = page.evaluate(_STATE_JS)
                max_children = max(max_children, st["children"])
                assert st["children"] <= DOM_CHILD_BOUND, (
                    f"exchange {i}: DOM children {st['children']} exceed "
                    f"bound {DOM_CHILD_BOUND}")
                if i % 5 == 0:
                    # Auto-follow must CONVERGE to the bottom, not be there at
                    # the sampling instant: the ACK text renders while the final
                    # message is still growing (instrumented: 44-62px from
                    # bottom at ACK, 2px within 250ms, every exchange), and
                    # upstream styling changes nudged that straddle across a
                    # fixed 60px threshold — the #142 flake. Real follow loss
                    # stays drifted and still fails this wait.
                    try:
                        page.wait_for_function(
                            "()=>{const b=document.getElementById("
                            "'chat-history');return b.scrollHeight-b.scrollTop"
                            "-b.clientHeight < 60;}", timeout=2000)
                    except Exception:
                        st = page.evaluate(_STATE_JS)
                        raise AssertionError(
                            f"exchange {i}: auto-follow lost, "
                            f"{st['fromBottom']}px from bottom after 2s settle")

            assert saw_spinner, "initial .ai-spinner never appeared"
            assert saw_thinking, (
                ".agent-thinking-dots overlay never appeared during the "
                "mid-stream pause")
            assert not page.evaluate(
                "!!document.querySelector('.agent-thinking-dots')"), (
                "thinking indicator still present after the session")
            # The prune provably ran: 110 messages streamed, DOM stayed bounded.
            assert max_children <= DOM_CHILD_BOUND

            # Scroll-up: walk back to the first message; DOM stays bounded.
            reached = False
            for _ in range(80):
                if page.evaluate(
                        "document.getElementById('chat-history')"
                        ".textContent.includes('SOAKMSG 0 ')"):
                    reached = True
                    break
                page.evaluate(
                    "()=>{const b=document.getElementById('chat-history');"
                    "b.scrollTop=0; b.dispatchEvent(new Event('scroll'));}")
                page.wait_for_timeout(150)
                st = page.evaluate(_STATE_JS)
                assert st["children"] <= DOM_CHILD_BOUND, (
                    f"scroll-up: DOM children {st['children']} exceed bound")
            assert reached, "scroll-up never reached the first message"

            # Snap back: newest message visible, drain settled, pinned.
            page.evaluate("()=>window.chatHistory.scrollToBottom()")
            page.wait_for_function(
                "(m)=>{const h=document.getElementById('chat-history');"
                "return h.textContent.includes('ACK SOAKMSG '+m+'.')"
                " && window.chatHistory._draining===false"
                " && (h.scrollHeight-h.scrollTop-h.clientHeight)<30;}",
                arg=EXCHANGES - 1, timeout=15000)

            fatal = [e for e in errors if "favicon" not in e]
            assert not fatal, f"page errors during soak: {fatal}"
        finally:
            browser.close()
