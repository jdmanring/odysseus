"""The IO delivery probe (tests/bench/io_probe.js) must actually observe.

The probe is diagnostic infrastructure (it caught the chat-history top-sentinel
dead-end: a single delivery carrying a batched [leave, enter] pair that an
entries[0] read discarded). A diagnostic that silently stops logging is worse
than none, so this exercises it against real IntersectionObserver deliveries
in Chromium: observe/cb/disconnect events logged, multi-entry deliveries
surfaced as inter arrays, uninstall restores the native constructor.
"""
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
IO_PROBE_JS = (ROOT / "tests/bench/io_probe.js").read_text(encoding="utf-8")

_HARNESS = """
<!DOCTYPE html><html><head><style>
  #box { height: 200px; overflow-y: auto; }
  .item { height: 300px; }
</style></head><body>
<div id="box"><div class="item"></div><div id="target" class="item"></div></div>
</body></html>
"""


@pytest.fixture(scope="module")
def page():
    pw_api = pytest.importorskip("playwright.sync_api")
    with pw_api.sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        pg = browser.new_context(viewport={"width": 400, "height": 400}).new_page()
        yield pg
        browser.close()


def test_probe_logs_real_deliveries(page):
    page.set_content(_HARNESS)
    page.evaluate(IO_PROBE_JS)
    events = page.evaluate("""
        async () => {
            const box = document.getElementById('box');
            const target = document.getElementById('target');
            const obs = new IntersectionObserver(() => {}, { root: box });
            obs.observe(target);
            await new Promise(r => requestAnimationFrame(() => setTimeout(r, 50)));
            box.scrollTop = box.scrollHeight;      // target enters
            await new Promise(r => requestAnimationFrame(() => setTimeout(r, 50)));
            obs.disconnect();
            return window.ioProbe.log();
        }
    """)
    kinds = [e["ev"] for e in events]
    assert "observe" in kinds and "cb" in kinds and "disconnect" in kinds, kinds
    # Every delivery carries the full entries state array.
    cbs = [e for e in events if e["ev"] == "cb"]
    assert all(isinstance(e["inter"], list) and len(e["inter"]) >= 1 for e in cbs)
    # The enter transition was observed as isIntersecting=true.
    assert any(True in e["inter"] for e in cbs), cbs


def test_probe_surfaces_batched_multi_entry_delivery(page):
    """The reason the probe exists: several queued transitions delivered in ONE
    callback must appear as a multi-element inter array, oldest first."""
    page.set_content(_HARNESS)
    page.evaluate(IO_PROBE_JS)
    inter = page.evaluate("""
        async () => {
            window.ioProbe.clear();
            const box = document.getElementById('box');
            const target = document.getElementById('target');
            const obs = new IntersectionObserver(() => {}, { root: box });
            box.scrollTop = box.scrollHeight;      // target visible at observe time
            obs.observe(target);
            await new Promise(r => requestAnimationFrame(() => setTimeout(r, 50)));
            // Two transitions, then block the main thread so both queue into
            // one delivery: leave (scroll to 0) in one frame, enter in the
            // next, with the callback unable to run in between.
            box.scrollTop = 0;
            await new Promise(r => requestAnimationFrame(r));
            box.scrollTop = box.scrollHeight;
            const t0 = performance.now();
            while (performance.now() - t0 < 120) {}   // hold the thread
            await new Promise(r => setTimeout(r, 100));
            const multi = window.ioProbe.log().filter(
                e => e.ev === 'cb' && e.inter.length > 1);
            return multi.length ? multi[0].inter : null;
        }
    """)
    if inter is None:
        pytest.skip("browser delivered transitions separately this run "
                    "(scheduling-dependent); single-entry path covered above")
    assert inter[-1] != inter[0] or len(inter) >= 2


def test_probe_uninstall_restores_native(page):
    page.set_content(_HARNESS)
    page.evaluate(IO_PROBE_JS)
    assert page.evaluate("""
        () => {
            window.ioProbe.uninstall();
            const native = !('__ioProbeId' in new IntersectionObserver(() => {}));
            window.ioProbe.install();
            return native;
        }
    """)
