"""Guard tests for the benchmark's `hybrid` arm (tests/bench/vendor/hybrid_bench.js).

The hybrid arm is authored by the party with a stake in the benchmark's outcome, so
its claimed behaviour must be proven, not asserted. These run in real Chromium and
check the three things the arm claims:

  1. warm band detaches (children removed, height pinned, children still referenced)
  2. cold tail evicts (wrapper removed from the DOM entirely, children dropped)
  3. both bands restore on scroll-back, and no message is lost

If any of these fail, the arm is not a hybrid and its benchmark numbers are void.
"""
import pathlib

import pytest

playwright = pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
HYBRID_JS = ROOT / "tests/bench/vendor/hybrid_bench.js"

HTML = """
<!DOCTYPE html><html><head><style>
  body { margin: 0; }
  #chat-history { height: 700px; overflow-y: auto; display: flex; flex-direction: column; }
  .msg { flex-shrink: 0; box-sizing: border-box; padding: 8px; border-bottom: 1px solid #333; }
</style></head><body>
<div id="chat-history" role="log"></div>
<script>
  window.chatModule = { addMessage: function (role, content) {
    var d = document.createElement('div');
    d.className = 'msg msg-' + role;
    d.innerHTML = content;
    document.getElementById('chat-history').appendChild(d);
    return d;
  } };
</script></body></html>
"""

N = 400
CORPUS = (
    "["
    + ",".join(
        '{"role":"%s","content":"<p>Message %d. %s</p>"}'
        % ("user" if i % 2 == 0 else "assistant", i, "Lorem ipsum dolor sit amet. " * 6)
        for i in range(N)
    )
    + "]"
)


@pytest.fixture(scope="module")
def page():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        pg = browser.new_page(viewport={"width": 900, "height": 700})
        yield pg
        browser.close()


def _load(page):
    page.set_content(HTML)
    page.add_script_tag(path=str(HYBRID_JS))
    page.evaluate(f"() => window.hybridBench.load({CORPUS})")
    page.wait_for_timeout(250)
    return page


def _settle(page, frames=6):
    page.evaluate(
        """async (n) => { for (let i = 0; i < n; i++)
             await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))); }""",
        frames,
    )
    page.wait_for_timeout(120)


def test_cold_tail_is_evicted_not_merely_detached(page):
    """Only a bounded window of wrappers exists in the DOM; the rest are gone."""
    _load(page)
    stats = page.evaluate("() => window.hybridBench.stats()")
    assert stats["total"] == N
    assert stats["rendered"] <= 80, stats
    wrappers = page.evaluate("() => document.querySelectorAll('#chat-history .msg').length")
    assert wrappers == stats["rendered"]
    # An evicted message contributes zero DOM nodes, unlike #4998's pinned wrapper.
    assert wrappers < N / 2


def test_warm_band_detaches_children_and_pins_height(page):
    """Off-screen-but-in-window wrappers keep their box but lose their children."""
    _load(page)
    _settle(page)
    info = page.evaluate(
        """() => {
            const nodes = [...document.querySelectorAll('#chat-history .msg')];
            const collapsed = nodes.filter(n => n.__vCollapsed);
            return {
              collapsed: collapsed.length,
              allEmpty: collapsed.every(n => n.childNodes.length === 0),
              allPinned: collapsed.every(n => parseFloat(n.style.minHeight) > 0),
              childrenKept: collapsed.every(n => (n.__vChildren || []).length > 0),
              heightsNonZero: collapsed.every(n => n.getBoundingClientRect().height > 0),
            };
        }"""
    )
    assert info["collapsed"] > 0, "warm band never detached anything"
    assert info["allEmpty"] and info["allPinned"]
    assert info["childrenKept"], "detached children must stay referenced for cheap restore"
    assert info["heightsNonZero"], "pinned height must hold the scroll geometry open"


def test_warm_restore_reattaches_without_reparse(page):
    """Scrolling a collapsed wrapper back into view re-appends its original nodes."""
    _load(page)
    _settle(page)
    page.evaluate(
        """() => {
            const n = [...document.querySelectorAll('#chat-history .msg')].find(x => x.__vCollapsed);
            n.__probe = n.__vChildren[0];       // identity of the very node detached
            window.__target = n;
            n.scrollIntoView();
        }"""
    )
    _settle(page)
    res = page.evaluate(
        """() => ({ collapsed: !!window.__target.__vCollapsed,
                    sameNode: window.__target.firstChild === window.__target.__probe,
                    minHeight: window.__target.style.minHeight })"""
    )
    assert res["collapsed"] is False
    assert res["sameNode"], "restore must re-append the SAME node, not re-parse HTML"
    assert res["minHeight"] == ""


def test_scroll_to_top_pages_in_cold_tail_and_loses_nothing(page):
    """The cold tail re-materializes from source; message 0 is reachable."""
    _load(page)
    page.evaluate(
        """async () => {
            const box = document.getElementById('chat-history');
            for (let i = 0; i < 400 && window.hybridBench.stats().lo > 0; i++) {
              box.scrollTop = 0;
              await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
            }
        }"""
    )
    _settle(page)
    stats = page.evaluate("() => window.hybridBench.stats()")
    assert stats["lo"] == 0, f"sweep never reached the true top: {stats}"
    assert stats["rendered"] <= 80, "window must stay bounded even at the top"
    assert page.evaluate(
        "() => !!document.querySelector('#chat-history').textContent.match(/Message 0\\./)"
    ), "message 0 was lost"


def test_bounded_window_holds_after_full_traversal(page):
    """Memory bound is not a load-time artifact: it survives a bottom->top->bottom trip."""
    _load(page)
    page.evaluate(
        """async () => {
            const box = document.getElementById('chat-history');
            for (const y of [0, 0, 0, 1e9, 1e9, 0, 1e9]) {
              for (let i = 0; i < 60; i++) {
                box.scrollTop = y;
                await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
              }
            }
        }"""
    )
    _settle(page)
    stats = page.evaluate("() => window.hybridBench.stats()")
    assert stats["rendered"] <= 80, stats
    assert stats["total"] == N, "traversal must not duplicate or drop source messages"
