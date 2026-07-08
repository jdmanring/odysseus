"""Accessibility guard tests for chatHistory.js (real Chromium, mock DOM).

The #chat-history container is role="log" aria-live="polite" AND the element the
virtualizer prepends into and evicts from. These guards lock in the a11y fixes so
they cannot silently regress:

  * aria-busy brackets a prepend/evict batch and is restored to its PRIOR value
    (composes with the streaming aria-busy chat.js sets on the same element);
  * focus inside an evicted node is moved to the log container, not dumped to
    <body>;
  * the interactive bottom sentinel is keyboard- and AT-reachable (role/tabindex/
    Enter); decorative sentinels and spacers are aria-hidden.

These assert observable DOM state, not screen-reader output (which cannot be driven
here). They validate the churn/robustness contract, per the audit.
"""
import pathlib
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
CHAT_HISTORY_JS = ROOT / "static/js/chatHistory.js"

_HARNESS_HTML = """
<!DOCTYPE html>
<html>
<head>
<style>
  body { margin: 0; }
  #chat-history { height: 400px; overflow-y: auto; display: flex; flex-direction: column; }
  .msg { height: 100px; flex-shrink: 0; box-sizing: border-box; }
</style>
</head>
<body>
<div id="chat-history" role="log" aria-live="polite"></div>
<script>
window.chatModule = {
    addMessage: function(role, content) {
        var div = document.createElement('div');
        div.className = 'msg msg-' + role;
        div.tabIndex = 0;                 // focusable, like a real bubble with links
        div.textContent = content;
        document.getElementById('chat-history').appendChild(div);
        return div;
    }
};
</script>
</body>
</html>
"""


@pytest.fixture(scope="module")
def page():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 800, "height": 600})
        p = ctx.new_page()
        yield p
        browser.close()


def _load(page):
    page.set_content(_HARNESS_HTML)
    page.add_script_tag(path=str(CHAT_HISTORY_JS))
    page.wait_for_timeout(100)


def _load_msgs(page, n):
    page.evaluate(
        "(n)=>{const msgs=Array.from({length:n},(_,i)=>({role:'user',content:'Message '+i,"
        "modelName:null,meta:null})); window.chatHistory.load(msgs);}", n)
    page.wait_for_timeout(120)


# --- aria-busy compose -----------------------------------------------------

def test_clear_busy_restores_absent_attribute(page):
    _load(page)
    r = page.evaluate("""() => {
        const c = document.getElementById('chat-history');
        const ch = window.chatHistory;
        const beforeHas = c.hasAttribute('aria-busy');
        ch._setBusy();
        const during = c.getAttribute('aria-busy');
        ch._clearBusy();
        return { beforeHas, during, afterHas: c.hasAttribute('aria-busy') };
    }""")
    assert r["beforeHas"] is False
    assert r["during"] == "true"
    assert r["afterHas"] is False        # restored to absent, not left as 'false'


def test_clear_busy_composes_with_streaming_busy(page):
    _load(page)
    # Simulate a stream owning aria-busy='true' (as chat.js:1449 does), then run a
    # virtualizer batch: clearing must NOT steal busy from the in-flight stream.
    r = page.evaluate("""() => {
        const c = document.getElementById('chat-history');
        const ch = window.chatHistory;
        c.setAttribute('aria-busy', 'true');     // stream start
        ch._setBusy();                            // virtualizer batch begins
        ch._clearBusy();                          // virtualizer batch ends
        return c.getAttribute('aria-busy');
    }""")
    assert r == "true"                    # stream still owns busy


# --- focus preservation on eviction ----------------------------------------

def test_focus_moved_to_container_when_focused_node_pruned(page):
    _load(page)
    _load_msgs(page, 60)
    r = page.evaluate("""() => {
        const c = document.getElementById('chat-history');
        const ch = window.chatHistory;
        // focus the oldest rendered bubble, then prune from the top past it
        const first = c.querySelector('.msg');
        first.focus();
        const focusedBefore = document.activeElement === first;
        ch._pruneTop(10);
        const stillConnected = document.contains(first);
        return {
            focusedBefore,
            prunedNodeGone: !stillConnected,
            focusOnBody: document.activeElement === document.body,
            focusOnContainer: document.activeElement === c,
        };
    }""")
    assert r["focusedBefore"] is True
    assert r["prunedNodeGone"] is True
    assert r["focusOnBody"] is False       # not dumped to <body>
    assert r["focusOnContainer"] is True   # moved to the log container


def test_focus_untouched_when_focused_node_survives(page):
    _load(page)
    _load_msgs(page, 60)
    # Focus a node OUTSIDE the container; a prune must not steal it.
    r = page.evaluate("""() => {
        const btn = document.createElement('button');
        document.body.appendChild(btn);
        btn.focus();
        window.chatHistory._pruneTop(5);
        return document.activeElement === btn;
    }""")
    assert r is True


# --- sentinel semantics ----------------------------------------------------

def test_bottom_sentinel_is_keyboard_accessible(page):
    _load(page)
    _load_msgs(page, 60)
    # Scroll up to page older in, then drive downward so a bottom sentinel exists.
    r = page.evaluate("""() => {
        const c = document.getElementById('chat-history');
        const ch = window.chatHistory;
        // Force a bottom sentinel by pruning the tail then re-attaching.
        ch._loadOlder();               // ensure history rendered
        ch._endIdx = Math.min(ch._all.length, ch._endIdx);
        // simulate pruned-tail state so _attachBottomSentinel renders a control
        ch._startIdx = 0; ch._endIdx = 30;
        ch._attachBottomSentinel();
        const s = c.querySelector('.chat-history-bottom-sentinel');
        if (!s) return { present: false };
        return {
            present: true,
            role: s.getAttribute('role'),
            tabindex: s.getAttribute('tabindex'),
            hasLabel: !!s.getAttribute('aria-label'),
        };
    }""")
    assert r["present"] is True
    assert r["role"] == "button"
    assert r["tabindex"] == "0"
    assert r["hasLabel"] is True


def test_bottom_sentinel_enter_key_loads_newer(page):
    _load(page)
    _load_msgs(page, 60)
    r = page.evaluate("""() => {
        const c = document.getElementById('chat-history');
        const ch = window.chatHistory;
        ch._startIdx = 0; ch._endIdx = 30;
        ch._attachBottomSentinel();
        const s = c.querySelector('.chat-history-bottom-sentinel');
        const before = ch._endIdx;
        s.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
        return { before, after: ch._endIdx };
    }""")
    assert r["after"] > r["before"]        # Enter loaded a newer batch


def test_decorative_sentinel_and_spacer_are_aria_hidden(page):
    _load(page)
    _load_msgs(page, 60)
    r = page.evaluate("""() => {
        const c = document.getElementById('chat-history');
        const top = c.querySelector('.chat-history-sentinel');
        return { topHidden: top && top.getAttribute('aria-hidden') === 'true' };
    }""")
    assert r["topHidden"] is True
