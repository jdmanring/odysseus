"""Playwright browser tests for chatHistory.js DOM virtualization.

Runs chatHistory.js in real Chromium with a minimal mock DOM so we can verify
actual browser behaviour: IntersectionObserver firing on scroll, DOM child count
staying bounded, scroll position preservation, and session reset.

Run with:
    venv/bin/python3 -m pytest tests/test_chat_history_playwright.py -v

or via the project's standard discovery:
    python3 -m unittest discover -s tests -p "test_chat_history_playwright.py"
"""
import pathlib
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
CHAT_HISTORY_JS = ROOT / "static/js/chatHistory.js"

# ---------------------------------------------------------------------------
# HTML harness — minimal mock DOM loaded by Playwright
# ---------------------------------------------------------------------------
# #chat-history is a fixed-height scroll container so IntersectionObserver
# fires when the sentinel enters the visible area of the scroll container.
# addMessage() appends a 100px div and returns it, matching chatRenderer.js.

_HARNESS_HTML = """
<!DOCTYPE html>
<html>
<head>
<style>
  body { margin: 0; }
  #chat-history {
    height: 400px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
  }
  .msg { height: 100px; flex-shrink: 0; box-sizing: border-box; }
</style>
</head>
<body>
<div id="chat-history"></div>
<script>
window.chatModule = {
    _callCount: 0,
    addMessage: function(role, content, modelName, meta) {
        window.chatModule._callCount++;
        var div = document.createElement('div');
        div.className = 'msg msg-' + role;
        div.dataset.role = role;
        div.textContent = content;
        document.getElementById('chat-history').appendChild(div);
        return div;
    }
};
</script>
</body>
</html>
"""


def _make_messages(n, role="user"):
    return [{"role": role, "content": "Message " + str(i), "modelName": None, "meta": None}
            for i in range(n)]


@pytest.fixture(scope="module")
def browser_page():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 800, "height": 600})
        page = ctx.new_page()
        yield page
        browser.close()


def _load_harness(page):
    """Load the HTML harness then inject chatHistory.js."""
    page.set_content(_HARNESS_HTML)
    page.add_script_tag(path=str(CHAT_HISTORY_JS))
    # Give MutationObserver / IntersectionObserver time to initialise
    page.wait_for_timeout(100)


# ---------------------------------------------------------------------------
# Phase 1 — load-time windowing
# ---------------------------------------------------------------------------

def test_sentinel_appears_when_session_exceeds_window(browser_page):
    """Loading 60 messages renders 50 and shows a sentinel for the rest.

    load() scrolls the container to the bottom after rendering so the sentinel
    (prepended at the top) is out of view and the IntersectionObserver doesn't
    fire immediately.
    """
    _load_harness(browser_page)

    browser_page.evaluate("""
        const msgs = Array.from({length: 60}, (_, i) => ({
            role: 'user', content: 'Message ' + i, modelName: null, meta: null
        }));
        window.chatHistory.load(msgs);
    """)
    # Give IO one frame to settle — sentinel should NOT fire (container is at bottom)
    browser_page.wait_for_timeout(100)

    # DOM: 50 messages + sentinel + hist-sep + honesty spacer = 53 children
    total = browser_page.evaluate("document.getElementById('chat-history').children.length")
    assert total == 53, f"expected 53 children (50 msgs + sentinel + sep + spacer), got {total}"

    sentinel_text = browser_page.evaluate(
        "document.querySelector('.chat-history-sentinel').textContent"
    )
    assert "10 earlier messages" in sentinel_text, sentinel_text


def test_no_sentinel_when_session_fits_in_window(browser_page):
    """Sessions with ≤50 messages render everything with no sentinel."""
    _load_harness(browser_page)

    browser_page.evaluate("""
        const msgs = Array.from({length: 30}, (_, i) => ({
            role: 'user', content: 'Msg ' + i, modelName: null, meta: null
        }));
        window.chatHistory.load(msgs);
    """)
    browser_page.wait_for_timeout(200)

    # 30 msgs + 1 hist-sep = 31 (no sentinel when session fits in window)
    total = browser_page.evaluate("document.getElementById('chat-history').children.length")
    assert total == 31
    has_sentinel = browser_page.evaluate(
        "!!document.querySelector('.chat-history-sentinel')"
    )
    assert not has_sentinel


def test_load_older_prepends_batch_on_scroll(browser_page):
    """Scrolling to the top triggers _loadOlder and adds 25 messages."""
    _load_harness(browser_page)

    browser_page.evaluate("""
        const msgs = Array.from({length: 100}, (_, i) => ({
            role: 'user', content: 'Msg ' + i, modelName: null, meta: null
        }));
        window.chatHistory.load(msgs);
    """)
    # load() scrolls to bottom; wait for IO to settle (sentinel must NOT fire yet)
    browser_page.wait_for_timeout(200)

    # Initial: 50 msgs + sentinel + hist-sep + honesty spacer = 53
    before = browser_page.evaluate(
        "document.getElementById('chat-history').children.length"
    )
    assert before == 53, f"expected 53 initial children, got {before}"

    # Scroll to the absolute top. With the honesty spacer this is a position
    # inside the estimated unrendered range, so the catch-up chain drains
    # batches until real content reaches the held position — i.e. the oldest
    # message — while the DOM stays bounded by the Phase-3 caps.
    browser_page.evaluate("document.getElementById('chat-history').scrollTop = 0")
    browser_page.wait_for_timeout(500)

    assert browser_page.evaluate("window.chatHistory._startIdx") == 0
    dom_text = browser_page.evaluate("document.getElementById('chat-history').textContent")
    assert "Msg 0" in dom_text, "oldest message must be rendered after top-pinned load"
    n_msgs = browser_page.evaluate("""
        new Set([...document.querySelectorAll('#chat-history [data-ch-idx]')]
            .map(e => e.dataset.chIdx)).size
    """)
    assert n_msgs < 100, f"DOM must stay bounded during the drain, got {n_msgs} msgs"


def test_scroll_position_preserved_after_load_older(browser_page):
    """Prepending messages must not cause the visible area to jump."""
    _load_harness(browser_page)

    browser_page.evaluate("""
        const msgs = Array.from({length: 80}, (_, i) => ({
            role: 'user', content: 'Msg ' + i, modelName: null, meta: null
        }));
        window.chatHistory.load(msgs);
    """)
    browser_page.wait_for_timeout(200)

    # Message-anchored invariant (measure in messages, not pixels): position
    # the viewport on a RENDERED message just below the honesty spacer, prepend
    # a batch, and the anchor message must not move in the viewport. The old
    # pixel assertion (scrollTop != 0 after compensation) is meaningless now
    # that scrollTop=0 is a valid held position inside the estimated range.
    anchor_top_before = browser_page.evaluate("""
        (() => {
            const c = document.getElementById('chat-history');
            const first = c.querySelector('[data-ch-idx]');
            c.scrollTop = first.offsetTop + 400;  // rendered content, beyond the 300px rootMargin (no IO overlap)
            window.__anchor = first;
            return first.getBoundingClientRect().top;
        })()
    """)
    browser_page.evaluate("window.chatHistory._loadOlder()")
    browser_page.wait_for_timeout(300)
    anchor_top_after = browser_page.evaluate(
        "window.__anchor.getBoundingClientRect().top"
    )
    assert abs(anchor_top_after - anchor_top_before) <= 2, (
        f"anchor message moved {anchor_top_after - anchor_top_before:+.0f}px in "
        f"the viewport after a prepend — compensation broken"
    )
    # And the batch really was prepended.
    assert browser_page.evaluate("window.chatHistory._startIdx") == 5


# ---------------------------------------------------------------------------
# Session reset
# ---------------------------------------------------------------------------

def test_reset_clears_sentinel_and_state(browser_page):
    """reset() removes the sentinel and prepares for a new session load."""
    _load_harness(browser_page)

    browser_page.evaluate("""
        const msgs = Array.from({length: 60}, (_, i) => ({
            role: 'user', content: 'Msg ' + i, modelName: null, meta: null
        }));
        window.chatHistory.load(msgs);
    """)
    # load() scrolls to bottom; wait for IO to settle
    browser_page.wait_for_timeout(200)

    # Confirm sentinel exists (load scrolled to bottom so sentinel is out of view)
    assert browser_page.evaluate("!!document.querySelector('.chat-history-sentinel')")

    # Reset and clear the container (as sessions.js does)
    browser_page.evaluate("""
        window.chatHistory.reset();
        document.getElementById('chat-history').innerHTML = '';
    """)
    browser_page.wait_for_timeout(100)

    # Sentinel should be gone
    assert not browser_page.evaluate("!!document.querySelector('.chat-history-sentinel')")

    # A fresh load of a short session should work correctly
    browser_page.evaluate("""
        const msgs = Array.from({length: 10}, (_, i) => ({
            role: 'user', content: 'New ' + i, modelName: null, meta: null
        }));
        window.chatHistory.load(msgs);
    """)
    browser_page.wait_for_timeout(200)

    # 10 msgs + 1 hist-sep = 11
    total = browser_page.evaluate("document.getElementById('chat-history').children.length")
    assert total == 11
    assert not browser_page.evaluate("!!document.querySelector('.chat-history-sentinel')")


# ---------------------------------------------------------------------------
# Phase 2 — live pruning guard (scroll-position check)
# ---------------------------------------------------------------------------

def test_prune_does_not_fire_when_scrolled_up(browser_page):
    """Phase 2 must not prune content while the user has scrolled up."""
    _load_harness(browser_page)

    browser_page.evaluate("""
        const msgs = Array.from({length: 50}, (_, i) => ({
            role: 'user', content: 'Msg ' + i, modelName: null, meta: null
        }));
        window.chatHistory.load(msgs);
    """)
    browser_page.wait_for_timeout(200)

    # Scroll user to top (not at bottom)
    browser_page.evaluate("document.getElementById('chat-history').scrollTop = 0")
    browser_page.wait_for_timeout(100)

    # Inject 40 more messages directly (simulating live streaming)
    browser_page.evaluate("""
        for (var i = 0; i < 40; i++) {
            window.chatModule.addMessage('assistant', 'Live msg ' + i, null, null);
        }
    """)
    browser_page.wait_for_timeout(300)

    # Live count: 50 loaded + 40 streamed = 90; PRUNE_AT is 80.
    # BUT user is scrolled up, so _isAtBottom() is false → no prune.
    live = browser_page.evaluate("""
        (function() {
            var ch = document.getElementById('chat-history').children;
            var n = 0;
            for (var i = 0; i < ch.length; i++) {
                var cls = ch[i].classList;
                if (!cls.contains('chat-history-sentinel') &&
                    !cls.contains('chat-history-spacer')   &&
                    !cls.contains('chat-history-sep')      &&
                    !cls.contains('chat-history-bottom-sentinel')) n++;
            }
            return n;
        })()
    """)
    assert live >= 85, (
        f"Phase 2 pruned while user was scrolled up (live count: {live})"
    )


# ---------------------------------------------------------------------------
# Phase 3 — bidirectional pruning
# ---------------------------------------------------------------------------

def test_bidi_prune_fires_on_deep_scroll_up(browser_page):
    """Scrolling up through enough history triggers bottom pruning (BIDI_CAP=120).

    With WINDOW_SIZE=50, BATCH_SIZE=25, BIDI_CAP=120:
    - After 4 scroll-up batches: 50+25+25+25+25 = 150 historical nodes > BIDI_CAP
    - _pruneBottom should fire and return historical count to BIDI_CAP (120)
    - A bottom sentinel should appear indicating pruned historical content.
    """
    _load_harness(browser_page)

    # 200 messages — far more than WINDOW_SIZE so Phase 1 gives us room to scroll
    browser_page.evaluate("""
        const msgs = Array.from({length: 200}, (_, i) => ({
            role: 'user', content: 'Msg ' + i, modelName: null, meta: null
        }));
        window.chatHistory.load(msgs);
    """)
    browser_page.wait_for_timeout(200)

    # Scroll up 4 times — each scroll-up adds 25 historical messages.
    # After batch 3 (50+25+25+25=125 > 120) bottom prune fires.
    for _ in range(4):
        browser_page.evaluate("document.getElementById('chat-history').scrollTop = 0")
        browser_page.wait_for_timeout(600)

    hist_count = browser_page.evaluate("""
        (function() {
            var c = document.getElementById('chat-history');
            var sep = c.querySelector('.chat-history-sep');
            if (!sep) return c.children.length;
            var n = 0;
            for (var i = 0; i < c.children.length; i++) {
                if (c.children[i] === sep) break;
                var cls = c.children[i].classList;
                if (!cls.contains('chat-history-sentinel') &&
                    !cls.contains('chat-history-spacer') &&
                    !cls.contains('chat-history-bottom-sentinel')) n++;
            }
            return n;
        })()
    """)
    # Historical count must be capped at BIDI_CAP (120) by the time prune fires
    assert hist_count <= 125, (
        f"Bidirectional prune did not fire: {hist_count} historical nodes in DOM"
    )

    has_bottom_sentinel = browser_page.evaluate(
        "!!document.querySelector('.chat-history-bottom-sentinel')"
    )
    assert has_bottom_sentinel, (
        "Bottom sentinel should appear after bidirectional prune"
    )


def test_bidi_cap_held_during_scroll_down(browser_page):
    """Historical DOM count must stay bounded during scroll-down, not just scroll-up.

    Without top-pruning in _loadNewer, a full up-then-down cycle reloads every
    message into the DOM. After the fix, _loadNewer prunes from the top as it
    adds at the bottom, keeping histChildCount at or near BIDI_CAP throughout.
    """
    _load_harness(browser_page)

    browser_page.evaluate("""
        const msgs = Array.from({length: 200}, (_, i) => ({
            role: 'user', content: 'Msg ' + i, modelName: null, meta: null
        }));
        window.chatHistory.load(msgs);
    """)
    browser_page.wait_for_timeout(200)

    # Scroll all the way up to trigger bidi pruning
    for _ in range(7):
        browser_page.evaluate("document.getElementById('chat-history').scrollTop = 0")
        browser_page.wait_for_timeout(600)

    # Now scroll all the way back down, triggering _loadNewer repeatedly
    for _ in range(7):
        browser_page.evaluate(
            "document.getElementById('chat-history').scrollTop = "
            "document.getElementById('chat-history').scrollHeight"
        )
        browser_page.wait_for_timeout(600)

    hist_count = browser_page.evaluate("""
        (function() {
            var c = document.getElementById('chat-history');
            var sep = c.querySelector('.chat-history-sep');
            var n = 0;
            for (var i = 0; i < c.children.length; i++) {
                if (c.children[i] === sep) break;
                var cls = c.children[i].classList;
                if (!cls.contains('chat-history-sentinel') &&
                    !cls.contains('chat-history-spacer') &&
                    !cls.contains('chat-history-bottom-sentinel')) n++;
            }
            return n;
        })()
    """)
    # Allow BIDI_CAP + one batch of headroom
    assert hist_count <= 145, (
        f"_loadNewer failed to prune top: {hist_count} historical nodes after full "
        f"down-scroll (expected ≤ 145, BIDI_CAP=120 + BATCH_SIZE=25)"
    )


def test_load_newer_fires_on_bottom_sentinel(browser_page):
    """Scrolling to the bottom sentinel loads historical messages downward.

    After triggering bidirectional pruning, scrolling down to the bottom sentinel
    should call _loadNewer() and restore pruned historical content.
    """
    _load_harness(browser_page)

    browser_page.evaluate("""
        const msgs = Array.from({length: 200}, (_, i) => ({
            role: 'user', content: 'Msg ' + i, modelName: null, meta: null
        }));
        window.chatHistory.load(msgs);
    """)
    browser_page.wait_for_timeout(200)

    # Scroll up enough to trigger bottom prune
    for _ in range(4):
        browser_page.evaluate("document.getElementById('chat-history').scrollTop = 0")
        browser_page.wait_for_timeout(600)

    # Confirm bottom sentinel exists
    has_bot = browser_page.evaluate(
        "!!document.querySelector('.chat-history-bottom-sentinel')"
    )
    assert has_bot, "Setup: bottom sentinel must exist before testing _loadNewer"

    end_idx_before = browser_page.evaluate("window.chatHistory._endIdx")

    # Scroll to where the bottom sentinel is — it should be just above the separator
    browser_page.evaluate("""
        var s = document.querySelector('.chat-history-bottom-sentinel');
        if (s) s.scrollIntoView();
    """)
    browser_page.wait_for_timeout(600)

    end_idx_after = browser_page.evaluate("window.chatHistory._endIdx")
    assert end_idx_after > end_idx_before, (
        f"_loadNewer did not fire: _endIdx unchanged at {end_idx_after}"
    )


# ---------------------------------------------------------------------------
# Phase 2 — live pruning positive case
# ---------------------------------------------------------------------------

def test_prune_fires_when_at_bottom(browser_page):
    """Phase 2: pruning fires and inserts a spacer when node count exceeds
    PRUNE_AT (80) while the user is at the scroll bottom.

    The existing test only covers the negative case (pruning suppressed while
    user is scrolled up). This covers the positive case — the primary reason
    Phase 2 exists.
    """
    _load_harness(browser_page)

    # Load exactly WINDOW_SIZE (50) messages so the DOM starts at capacity.
    browser_page.evaluate("""
        const msgs = Array.from({length: 50}, (_, i) => ({
            role: 'user', content: 'Hist ' + i, modelName: null, meta: null
        }));
        window.chatHistory.load(msgs);
    """)
    browser_page.wait_for_timeout(200)

    # Confirm the user is at scroll bottom after load().
    at_bottom = browser_page.evaluate("""
        (function() {
            var c = document.getElementById('chat-history');
            return c.scrollHeight - c.scrollTop - c.clientHeight < 30;
        })()
    """)
    assert at_bottom, "Setup: expected to be at scroll bottom after load()"

    # Inject 35 live messages — total 85 children > PRUNE_AT (80).
    # The mock addMessage() does not auto-scroll, so scrollTop would stall at the
    # pre-injection position while scrollHeight grows.  Snap to bottom inside the
    # same evaluate() call so the position is updated before the MutationObserver
    # rAF callback runs and _isAtBottom() is evaluated.
    browser_page.evaluate("""
        for (var i = 0; i < 35; i++) {
            window.chatModule.addMessage('assistant', 'Live ' + i, null, null);
        }
        var c = document.getElementById('chat-history');
        c.scrollTop = c.scrollHeight;
    """)
    # MutationObserver fires asynchronously; two frames is enough.
    browser_page.wait_for_timeout(300)

    # A spacer must have been inserted (confirms _pruneTop() ran).
    has_spacer = browser_page.evaluate(
        "!!document.querySelector('.chat-history-spacer')"
    )
    assert has_spacer, (
        "Phase 2 did not fire: no spacer found after 85 DOM children at scroll bottom "
        "(PRUNE_AT=80, PRUNE_COUNT=20 should have reduced count to ~65)"
    )

    # Non-control node count must now be below PRUNE_AT.
    count = browser_page.evaluate("""
        (function() {
            var ch = document.getElementById('chat-history').children;
            var n = 0;
            for (var i = 0; i < ch.length; i++) {
                var cls = ch[i].classList;
                if (!cls.contains('chat-history-sentinel') &&
                    !cls.contains('chat-history-spacer')   &&
                    !cls.contains('chat-history-sep')      &&
                    !cls.contains('chat-history-bottom-sentinel')) n++;
            }
            return n;
        })()
    """)
    assert count <= 70, (
        f"Phase 2 did not reduce DOM children: {count} still present (expected ≤70 "
        f"after PRUNE_COUNT=20 removal from 85)"
    )


# ---------------------------------------------------------------------------
# _gen counter — session-switch safety
# ---------------------------------------------------------------------------

def test_gen_counter_prevents_old_session_content_after_switch(browser_page):
    """Switching sessions must not bleed content from the outgoing session.

    The _gen counter is incremented in reset(). Any rAF callback scheduled
    during the prior load() captures the old gen value and bails when it fires
    after the counter has changed, so it cannot mutate the new session's DOM.
    """
    _load_harness(browser_page)

    # Load first session (large), then switch immediately inside the same JS
    # task before any rAF from the first load() fires.
    browser_page.evaluate("""
        var oldMsgs = Array.from({length: 200}, (_, i) => ({
            role: 'user', content: 'OldSession ' + i, modelName: null, meta: null
        }));
        window.chatHistory.load(oldMsgs);

        // Simulate what sessions.js does on session switch.
        window.chatHistory.reset();
        document.getElementById('chat-history').innerHTML = '';

        var newMsgs = Array.from({length: 8}, (_, i) => ({
            role: 'assistant', content: 'NewSession ' + i, modelName: null, meta: null
        }));
        window.chatHistory.load(newMsgs);
    """)
    # Allow rAF callbacks from the first load() to fire and (correctly) bail.
    browser_page.wait_for_timeout(500)

    texts = browser_page.evaluate("""
        Array.from(document.querySelectorAll('.msg')).map(function(m) {
            return m.textContent;
        })
    """)

    leaked = [t for t in texts if "OldSession" in t]
    assert not leaked, (
        f"Old session content leaked after switch (gen counter may have failed): "
        f"{leaked[:3]}"
    )
    assert len(texts) == 8, (
        f"Expected 8 new-session messages, got {len(texts)} — session switch may "
        f"have left DOM in a partial state"
    )


# ---------------------------------------------------------------------------
# Server-paged history — scroll-up pulls older pages from the backend
#
# Upstream's /api/history caps a page at 100 messages; the virtualization holds
# only the pages fetched so far in _all. Without on-demand paging a long chat
# would only ever show its most recent page. These drive the REAL scroll +
# IntersectionObserver in Chromium with an injected olderLoader (the backend
# stand-in) to prove _fetchOlderFromServer fires, prepends, and terminates.
# ---------------------------------------------------------------------------

def test_server_paging_fetches_older_page_on_scroll(browser_page):
    """Scrolling to the top when the in-memory buffer is exhausted pulls the
    next older page from the backend and renders it."""
    _load_harness(browser_page)

    # History of 150 msgs; client initially loaded only the last 50 (one short
    # page). 100 older messages live on the "backend", served by olderLoader.
    browser_page.evaluate("""
        window.__olderCalls = [];
        const FULL = Array.from({length: 150}, (_, i) => ({
            role: 'user', content: 'Msg ' + i, modelName: null, meta: null
        }));
        window.chatHistory.load(FULL.slice(100), {
            sessionId: 's1',
            serverOffset: 100,
            serverHasMore: true,
            olderLoader: function (sid, limit, offset) {
                window.__olderCalls.push({ sid: sid, limit: limit, offset: offset });
                return Promise.resolve({
                    msgs: FULL.slice(offset, offset + limit),
                    offset: offset,
                    hasMore: offset > 0,
                });
            },
        });
    """)
    browser_page.wait_for_timeout(200)

    # Sentinel shows (server has more) but nothing fetched until the user scrolls.
    assert browser_page.evaluate("!!document.querySelector('.chat-history-sentinel')")
    assert browser_page.evaluate("window.__olderCalls.length") == 0
    sentinel = browser_page.evaluate("document.querySelector('.chat-history-sentinel').textContent")
    assert "100 earlier messages" in sentinel, sentinel

    browser_page.evaluate("document.getElementById('chat-history').scrollTop = 0")
    browser_page.wait_for_timeout(500)

    calls = browser_page.evaluate("window.__olderCalls")
    assert len(calls) == 1, f"expected one backend page fetch, got {calls}"
    assert calls[0]["sid"] == "s1"
    assert calls[0]["limit"] == 100 and calls[0]["offset"] == 0, calls[0]

    # Holding the absolute top chain-drains to the oldest message (the honesty
    # spacer keeps blank in view until the range is rendered), so the fetched
    # page's tail has already been rendered and bottom-pruned by the time we
    # look. The proof server paging worked end to end is the OLDEST message:
    # it only exists on the fetched page.
    dom_text = browser_page.evaluate("document.getElementById('chat-history').textContent")
    assert "Msg 0" in dom_text, "oldest server-paged message must be reachable on scroll-up"
    assert browser_page.evaluate("window.chatHistory._startIdx") == 0


def test_server_paging_iterates_multiple_pages_then_terminates(browser_page):
    """A history larger than one server page is fully reachable across several
    scroll-up fetches, and paging stops (sentinel gone) once offset hits 0."""
    _load_harness(browser_page)

    # 250 msgs; client loaded the last 50; 200 older on the backend => 2 pages.
    browser_page.evaluate("""
        window.__olderCalls = [];
        const FULL = Array.from({length: 250}, (_, i) => ({
            role: 'user', content: 'M' + i, modelName: null, meta: null
        }));
        window.chatHistory.load(FULL.slice(200), {
            sessionId: 's2',
            serverOffset: 200,
            serverHasMore: true,
            olderLoader: function (sid, limit, offset) {
                window.__olderCalls.push({ limit: limit, offset: offset });
                return Promise.resolve({
                    msgs: FULL.slice(offset, offset + limit),
                    offset: offset,
                    hasMore: offset > 0,
                });
            },
        });
    """)
    browser_page.wait_for_timeout(200)

    # Repeatedly scroll to the top; each _loadOlder walks 25 in-memory msgs and,
    # when the buffer is empty, pulls the next backend page.
    for _ in range(16):
        browser_page.evaluate("document.getElementById('chat-history').scrollTop = 0")
        browser_page.wait_for_timeout(250)

    calls = browser_page.evaluate("window.__olderCalls")
    offsets = [c["offset"] for c in calls]
    assert offsets == [100, 0], f"expected two pages at offset 100 then 0, got {offsets}"

    # The very first message (M0, from the oldest backend page) is reachable, and
    # the sentinel is gone once the backend is exhausted (offset hit 0).
    has_m0 = browser_page.evaluate(
        "Array.from(document.querySelectorAll('.msg')).some(function(m){return m.textContent === 'M0';})"
    )
    assert has_m0, "oldest message must be reachable after paging back through the backend"
    has_sentinel = browser_page.evaluate("!!document.querySelector('.chat-history-sentinel')")
    assert not has_sentinel, "sentinel must disappear once the backend is exhausted"
    assert browser_page.evaluate("window.chatHistory._serverHasMore") is False


def test_server_paging_drops_stale_result_after_reset(browser_page):
    """A page that lands after the session switched (reset) must be discarded —
    the _gen guard prevents another chat's history from leaking in."""
    _load_harness(browser_page)

    browser_page.evaluate("""
        window.__resolve = null;
        const FULL = Array.from({length: 100}, (_, i) => ({
            role: 'user', content: 'Old' + i, modelName: null, meta: null
        }));
        window.chatHistory.load(FULL.slice(50), {
            sessionId: 's3',
            serverOffset: 50,
            serverHasMore: true,
            olderLoader: function (sid, limit, offset) {
                return new Promise(function (res) {
                    window.__resolve = function () {
                        res({ msgs: FULL.slice(offset, offset + limit), offset: offset, hasMore: offset > 0 });
                    };
                });
            },
        });
    """)
    browser_page.wait_for_timeout(150)

    # Trigger the fetch (stays pending — the promise resolver is captured).
    browser_page.evaluate("document.getElementById('chat-history').scrollTop = 0")
    browser_page.wait_for_timeout(200)
    assert browser_page.evaluate("typeof window.__resolve === 'function'"), "fetch should be in flight"

    # Session switches (reset) BEFORE the stale page resolves.
    browser_page.evaluate("""
        window.chatHistory.reset();
        document.getElementById('chat-history').innerHTML = '';
        window.chatHistory.load([
            { role: 'assistant', content: 'FreshChat', modelName: null, meta: null }
        ]);
    """)
    browser_page.wait_for_timeout(100)

    # Now let the stale fetch resolve — it must be dropped by the gen guard.
    browser_page.evaluate("window.__resolve();")
    browser_page.wait_for_timeout(200)

    dom_text = browser_page.evaluate("document.getElementById('chat-history').textContent")
    assert "Old" not in dom_text, "stale server page leaked after reset (gen guard failed)"
    assert "FreshChat" in dom_text
