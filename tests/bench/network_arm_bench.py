#!/usr/bin/env python3
"""Network arm — the axis the main bench deliberately excludes, measured for real.

The main benchmark (chat_history_bench.py) serves cold pages from an in-memory
source, so eviction's deep scroll-back numbers there are a LOWER BOUND: in the
real app, every cold page the fork's MessageWindow re-renders is first fetched
from the server (`_fetchOlderFromServer` -> GET /api/history/{sid}?limit&offset),
while upstream PR #4998's detach-preserve restores from in-heap `__vChildren`
with ZERO network by construction. This arm quantifies that excluded cost.

What is real here (nothing synthetic in the measured path):
  * the actual FastAPI app (`import app`) under uvicorn, serving the actual
    /api/history route over real HTTP;
  * a real SQLite DB seeded with n messages whose content mix mirrors the main
    bench corpus (plain / fenced code / image / multi-block);
  * the fork's real client wiring — sessions.js selectSession installs the real
    olderLoader on the real MessageWindow; the excursion drives the same
    scroll-up path a user does.

What is emulated: round-trip latency, via CDP Network.emulateNetworkConditions,
because localhost RTT (~0) is the one unrepresentative link in an otherwise
real chain. RTT arms: 0 (localhost floor), 40 ms (broadband), 150 ms (mobile).

Measured per cell (median over --repeats, spread kept):
  walk_ms          wall time from bottom until the oldest message is rendered
  pages            /api/history requests issued during the walk
  wire_bytes       encoded bytes over the wire for those requests
  serialized: pages fetch one at a time (the client pages on demand), so added
  wall time ~= pages x RTT — the crossover claim this arm exists to test.

The detach comparison needs no browser run: its scroll-back network cost is
structurally zero (nodes never leave the heap). The honest comparison is
therefore "evict pays THIS much network; detach pays memory instead" — read
this artifact next to the main bench's USS tables, not instead of them.

Run:
    venv/bin/python tests/bench/network_arm_bench.py                # defaults
    venv/bin/python tests/bench/network_arm_bench.py --lengths 500,2000 --repeats 3
"""
import argparse
import json
import os
import pathlib
import platform
import signal
import socket
import statistics
import subprocess
import sys
import time
import urllib.request
import uuid
from datetime import datetime, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
RESULTS_DIR = ROOT / "tests/bench/results"
SID = "network-arm-bench"
VIEWPORT = {"width": 900, "height": 700}
RTTS_MS = [0, 40, 150]

_TINY_GIF = "data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw=="


# ---------------------------------------------------------------------------
# Corpus — same kind-mix as chat_history_bench._bubble_html, but as the MARKDOWN
# SOURCE the server stores (the wire carries stored source, not rendered HTML).
# SEQMSG markers let the excursion be defined in messages, per the main bench's
# probe-failure discipline.
# ---------------------------------------------------------------------------
def _message_md(i: int) -> str:
    kind = i % 10
    body = f"SEQMSG {i:04d}. " + ("Lorem ipsum dolor sit amet, consectetur adipiscing. " * 3)
    if kind in (0, 3, 6):  # markdown + fenced code (~30%)
        code = "\n".join(f"    line {j} of code block {i}" for j in range(8))
        body += f"\n\nHere is **bold** and `inline`:\n\n```\n{code}\n```"
    elif kind == 1:        # image (~10%)
        body += f"\n\nAn image:\n\n![img{i}]({_TINY_GIF})"
    elif kind == 2:        # multi-block (~10%), the agent multi-round proxy
        for r in range(4):
            body += f"\n\nRound {r} of agent message {i}. Reasoning text here."
    return body


def _seed(db_url: str, n: int) -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from core.database import Base, Session as DbSession, ChatMessage as DbChatMessage

    engine = create_engine(db_url)
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    try:
        db.add(DbSession(id=SID, name="Network Arm", endpoint_url="http://localhost/v1",
                         model="bench-model", owner=None))
        t = datetime(2026, 1, 1)
        for i in range(n):
            db.add(DbChatMessage(id=str(uuid.uuid4()), session_id=SID,
                                 role="user" if i % 2 == 0 else "assistant",
                                 content=_message_md(i), timestamp=t + timedelta(seconds=i)))
        db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Real server (the same bootstrap as tests/test_chat_history_render_paging_playwright.py)
# ---------------------------------------------------------------------------
def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class LiveServer:
    def __init__(self, datadir: str, n: int):
        self.datadir = datadir
        db_url = f"sqlite:///{datadir}/app.db"
        _seed(db_url, n)
        self.port = _free_port()
        env = dict(os.environ)
        env.update({"ODYSSEUS_DATA_DIR": datadir, "DATABASE_URL": db_url,
                    "AUTH_ENABLED": "false", "LOCALHOST_BYPASS": "true",
                    "APP_PORT": str(self.port)})
        self.proc = subprocess.Popen(
            [f"{ROOT}/venv/bin/python", "-c",
             f"import uvicorn, app; uvicorn.run(app.app, host='127.0.0.1', "
             f"port={self.port}, log_level='warning')"],
            cwd=str(ROOT), env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.base = f"http://127.0.0.1:{self.port}"
        for _ in range(120):
            try:
                urllib.request.urlopen(self.base + "/", timeout=2)
                return
            except Exception:
                time.sleep(0.5)
        self.stop()
        raise RuntimeError("server did not start")

    def stop(self) -> None:
        self.proc.send_signal(signal.SIGTERM)
        try:
            self.proc.wait(timeout=10)
        except Exception:
            self.proc.kill()

    def handler_latency_ms(self, n: int, samples: int = 7) -> dict:
        """Server-side page cost with no browser in the loop: time a cold mid-history
        page fetch (the shape the olderLoader issues). Median + spread over samples."""
        vals = []
        offset = max(0, n // 2 - 50)
        for _ in range(samples):
            t0 = time.perf_counter()
            urllib.request.urlopen(
                f"{self.base}/api/history/{SID}?limit=100&offset={offset}", timeout=10).read()
            vals.append((time.perf_counter() - t0) * 1000.0)
        return {"median_ms": round(statistics.median(vals), 2),
                "spread_ms": round(max(vals) - min(vals), 2)}


# ---------------------------------------------------------------------------
# The excursion — real client, real paging, wall-clocked in the page.
# ---------------------------------------------------------------------------
# Progress-driven, because MessageWindow's _loadOlder is NOT scroll-event-driven:
# it fires from an IntersectionObserver on a top sentinel (chatHistory.js, rootMargin
# 300px), which evaluates at frame boundaries. A fixed-cadence scrollTop=0 hammer
# races the post-prepend scroll re-anchor, so the sentinel is rarely intersecting
# when the observer evaluates — measured: 2 pages in 6000 iterations. A real user
# scrolls, waits for content, scrolls again; the driver does the same, and the
# wait-for-progress naturally absorbs whatever time the fetch round takes (which
# is exactly the quantity under test).
_WALK_JS = """
async () => {
  const box = document.getElementById('chat-history');
  const minIdx = () => {
    let best = Infinity;
    for (const el of box.querySelectorAll('.msg,.agent-thread')) {
      const m = /SEQMSG (\\d+)/.exec(el.textContent || '');
      if (m) best = Math.min(best, +m[1]);
    }
    return best;
  };
  box.scrollTop = box.scrollHeight;
  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  const t0 = performance.now();
  let prev = minIdx(), stalls = 0, rounds = 0;
  while (prev > 0 && stalls < 8 && rounds++ < 2000) {
    // Produce an intersection TRANSITION each round, and HOLD each phase for a
    // settled frame. Two measured failure modes shaped this:
    //   * pinning scrollTop at 0 deadlocks — a callback swallowed while _loading
    //     leaves the sentinel intersecting forever, so the observer never re-fires
    //     (stalled at scrollTop 0, _loading false, 800 buffered msgs unrendered);
    //   * a down-up jiggle inside one frame is invisible — IO evaluates once per
    //     frame after layout, so a transition that never survives to a frame
    //     boundary never happened (verified: the identical jiggle with holds
    //     resumed a 'stalled' walk instantly; a fresh observer fired fine).
    // A real user's scroll always spans frames; the driver must too.
    box.scrollTop = box.clientHeight * 2;
    await new Promise(r => requestAnimationFrame(r));
    await new Promise(r => setTimeout(r, 120));
    box.scrollTop = 0;
    await new Promise(r => requestAnimationFrame(r));
    box.dispatchEvent(new Event('scroll'));
    let cur = prev;
    for (let w = 0; w < 20; w++) {          // wait for progress, up to 1s per round
      await new Promise(r => setTimeout(r, 50));
      cur = minIdx();
      if (cur < prev) break;
    }
    stalls = cur < prev ? 0 : stalls + 1;
    prev = cur;
  }
  const ms = performance.now() - t0;
  return { ms: +ms.toFixed(0), complete: prev === 0, iters: rounds };
}
"""


def run_cell(pw, server: LiveServer, n: int, rtt_ms: int) -> dict:
    from urllib.parse import urlparse
    browser = pw.chromium.launch(headless=True)
    try:
        page = browser.new_context(viewport=VIEWPORT).new_page()
        cdp = page.context.new_cdp_session(page)
        cdp.send("Network.enable")

        hist_reqs: dict = {}
        bytes_done: list = []

        def on_sent(ev):
            url = ev.get("request", {}).get("url", "")
            if f"/api/history/{SID}" in url:
                hist_reqs[ev["requestId"]] = urlparse(url).query

        def on_fin(ev):
            if ev.get("requestId") in hist_reqs:
                bytes_done.append((hist_reqs[ev["requestId"]], ev.get("encodedDataLength", 0)))

        cdp.on("Network.requestWillBeSent", on_sent)
        cdp.on("Network.loadingFinished", on_fin)

        page.goto(server.base + "/", wait_until="networkidle", timeout=30000)
        page.wait_for_selector("#chat-history", timeout=15000)

        # Latency emulation starts AFTER app load: the claim under test is paging
        # cost, not asset-loading cost.
        cdp.send("Network.emulateNetworkConditions",
                 {"offline": False, "latency": rtt_ms,
                  "downloadThroughput": -1, "uploadThroughput": -1})

        page.evaluate(
            "async (sid)=>{await window.sessionModule.loadSessions();"
            " await window.sessionModule.selectSession(sid);}", SID)
        page.wait_for_function(
            "()=>document.querySelectorAll('#chat-history .msg,#chat-history .agent-thread').length>0",
            timeout=30000)
        page.wait_for_timeout(300)

        initial_pages = len(bytes_done)          # selectSession's own limit=100 fetch
        initial_bytes = sum(b for _, b in bytes_done)

        walk = page.evaluate(_WALK_JS)
        page.wait_for_timeout(200)               # let the last loadingFinished land

        walk_pages = len(bytes_done) - initial_pages
        walk_bytes = sum(b for _, b in bytes_done) - initial_bytes
        return {
            "n": n, "rtt_ms": rtt_ms,
            "walk_ms": walk["ms"], "complete": bool(walk["complete"]),
            "iters": walk["iters"],
            "pages": walk_pages, "wire_bytes": walk_bytes,
            "initial_pages": initial_pages, "initial_bytes": initial_bytes,
        }
    finally:
        browser.close()


def median_cell(pw, server, n, rtt_ms, repeats) -> dict:
    runs = [run_cell(pw, server, n, rtt_ms) for _ in range(repeats + 1)][1:]  # warm-up discard
    flags = [r["complete"] for r in runs]
    out = {"n": n, "rtt_ms": rtt_ms, "repeats_kept": len(runs),
           "complete": all(flags), "complete_runs": f"{sum(flags)}/{len(flags)}"}
    if not all(flags):
        # Same discipline as the main bench: a walk that never reached the oldest
        # message measured nothing; the cell must explain itself, not publish.
        out["withheld_reason"] = "walk never rendered the oldest message; timings withheld"
        return out
    for k in ("walk_ms", "pages", "wire_bytes", "iters"):
        vals = [r[k] for r in runs]
        out[k] = round(statistics.median(vals), 2)
        out[k + "_spread"] = round(max(vals) - min(vals), 2)
        out[k + "_raw"] = vals
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lengths", default="500,2000")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--rtts", default=",".join(str(r) for r in RTTS_MS))
    args = ap.parse_args()
    lengths = [int(x) for x in args.lengths.split(",")]
    rtts = [int(x) for x in args.rtts.split(",")]

    sys.path.insert(0, str(ROOT))
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright not installed", file=sys.stderr)
        sys.exit(1)

    import tempfile, shutil
    rows, handler = [], {}
    with sync_playwright() as pw:
        for n in lengths:
            datadir = tempfile.mkdtemp(prefix="netarm_")
            server = LiveServer(datadir, n)
            try:
                handler[n] = server.handler_latency_ms(n)
                print(f"n={n}: server handler {handler[n]['median_ms']}ms "
                      f"±{handler[n]['spread_ms']} per 100-msg page")
                for rtt in rtts:
                    cell = median_cell(pw, server, n, rtt, args.repeats)
                    rows.append(cell)
                    if cell["complete"]:
                        print(f"  n={n:5} rtt={rtt:3}ms  walk={cell['walk_ms']:8.0f}ms "
                              f"±{cell['walk_ms_spread']:<6.0f} pages={cell['pages']:.0f} "
                              f"wire={cell['wire_bytes']/1e3:.0f}kB")
                    else:
                        print(f"  n={n:5} rtt={rtt:3}ms  WITHHELD: {cell['withheld_reason']}")
            finally:
                server.stop()
                shutil.rmtree(datadir, ignore_errors=True)

    env = {"platform": platform.platform(), "python": platform.python_version(),
           "repeats_kept": args.repeats, "warmup_runs_discarded": 1,
           "server": "real app.py under uvicorn, real /api/history, seeded SQLite",
           "rtt_emulation": "CDP Network.emulateNetworkConditions, applied after app load",
           "detach_comparison": "structurally 0 pages / 0 bytes on scroll-back "
                                "(#4998 restores from in-heap __vChildren); not a measured cell"}
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = {"env": env, "server_handler_latency": handler, "results": rows}
    (RESULTS_DIR / "network_arm.json").write_text(json.dumps(out, indent=2))
    _write_markdown(rows, handler, lengths, rtts, env)
    print(f"\nWrote {RESULTS_DIR/'network_arm.json'} and {RESULTS_DIR/'network_arm.md'}")


def _write_markdown(rows, handler, lengths, rtts, env) -> None:
    by = {(r["n"], r["rtt_ms"]): r for r in rows}
    L = ["# Network arm results (generated)\n",
         "Generated by `tests/bench/network_arm_bench.py` (do not hand-edit). Medians over "
         f"{env['repeats_kept']} kept runs (1 warm-up discarded), `median ±(max-min)`.\n",
         "Real `app.py` under uvicorn; real `/api/history`; the fork's real MessageWindow + "
         "olderLoader wiring driven by scroll. RTT emulated via CDP after app load. "
         "`detach` (#4998) is structurally 0 pages / 0 bytes on scroll-back and has no cell here — "
         "read this next to the main bench's USS tables (memory is what detach pays instead).\n",
         "## Server handler latency (no browser): one cold 100-message page\n"]
    for n in lengths:
        h = handler.get(n) or handler.get(str(n))
        L.append(f"- n={n}: {h['median_ms']} ms ±{h['spread_ms']}")
    L.append("\n## Full walk to the oldest message — wall ms (real paging, RTT-emulated)\n")
    L.append("| n | " + " | ".join(f"RTT {r}ms" for r in rtts) + " |")
    L.append("|" + "---|" * (len(rtts) + 1))
    for n in lengths:
        cells = []
        for r in rtts:
            c = by[(n, r)]
            cells.append(f"{c['walk_ms']:.0f} ±{c['walk_ms_spread']:.0f}"
                         if c["complete"] else "—")
        L.append(f"| {n} | " + " | ".join(cells) + " |")
    L.append("\n## Pages fetched / bytes on the wire during the walk\n")
    L.append("| n | pages | wire kB |")
    L.append("|---|---|---|")
    for n in lengths:
        c = next((by[(n, r)] for r in rtts if by[(n, r)]["complete"]), None)
        if c:
            L.append(f"| {n} | {c['pages']:.0f} | {c['wire_bytes']/1e3:.0f} |")
        else:
            L.append(f"| {n} | — | — |")
    L.append("\nPages fetch one at a time (the client pages on demand), so added wall time "
             "≈ pages × RTT; the RTT columns above test that slope empirically.\n")
    (RESULTS_DIR / "network_arm.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
