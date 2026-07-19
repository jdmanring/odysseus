#!/usr/bin/env python3
"""mem-probe — read-only memory/CPU diagnostics for the Odysseus Qt wrapper.

Connects to the wrapper's Chrome DevTools endpoint (default localhost:9222) and
**correlates CDP metrics (JS heap, DOM counters, animation / rAF / mutation
activity) with the renderer process's OS-level RSS from /proc**. That correlation
is the point: in the QtWebEngine memory class this fork has been fighting, the JS
heap stays tiny (tens of MB) while the renderer process balloons to gigabytes,
because Qt never forwards an OS memory-pressure signal and reclaimable raster
tiles accumulate. A tool that only reads CDP heap numbers misses the whole
problem.

Why bespoke: the CDP client libraries (PyChromeDevTools, python-cdp,
browserdebuggertools, Playwright) are transport layers; none reads /proc renderer
RSS or names the on-page producer. This matches the wrapper's own approach of
hand-rolling CDP over a small dependency rather than pulling a framework.

ALL commands are READ-ONLY except `purge` (a deliberate reclaim). Nothing here
clears, pauses, or cancels page state — doing that destabilizes a live session
(a lesson learned the hard way).

Usage:
    venv/bin/python tooling/mem-probe.py <command> [options]

Commands:
    counters            RSS per QtWebEngine process, JS heap, DOM counters (one-shot)
    slope    [-d SECS]  sample RSS + DOM nodes over SECS; report MB/s and nodes/s
    animations          list running CSS animations (name, target, visible)
    raf      [-d SECS]  capture requestAnimationFrame scheduler call sites
    mutations[-d SECS]  capture which DOM nodes mutate (periodic DOM producers)
    producers[-d SECS]  animations + raf + mutations together (what is producing churn)
    purge               forciblyPurgeJavaScriptMemory; report RSS before/after
    chatdom  [-d SECS]  chat-history DOM children + px-from-bottom; one-shot, or
                        1 line/sec for SECS when -d is given (watch while scrolling)

Requires: websocket-client (already in the venv). Renderer RSS reading is Linux
(/proc) only; CDP commands work on any platform the wrapper runs on.
"""
import argparse
import glob
import json
import sys
import time
import urllib.request

try:
    import websocket  # websocket-client
except ImportError:
    sys.exit("mem-probe needs websocket-client. Run with: venv/bin/python tooling/mem-probe.py ...")


# --------------------------------------------------------------------------- #
# CDP transport (read-only by default)
# --------------------------------------------------------------------------- #
class CDP:
    def __init__(self, port=9222, timeout=30):
        targets = json.loads(urllib.request.urlopen(f"http://localhost:{port}/json", timeout=3).read())
        page = next((t for t in targets if t.get("type") == "page"), None)
        if not page:
            sys.exit(f"No page target on localhost:{port} — is the app running?")
        self.ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=timeout)
        self._id = 0

    def call(self, method, params=None):
        self._id += 1
        mid = self._id
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:
                return msg.get("result", {})

    def ev(self, expression, await_promise=False):
        """Runtime.evaluate, returning the JS value (handles the two-level result)."""
        r = self.call("Runtime.evaluate", {
            "expression": expression, "returnByValue": True, "awaitPromise": await_promise,
        })
        return r.get("result", {}).get("value")

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# Renderer process RSS from /proc (Linux)
# --------------------------------------------------------------------------- #
def qtwebengine_processes():
    """Return {pid: (type, rss_kb)} for each QtWebEngine process, type from --type=."""
    out = {}
    import re
    for d in glob.glob("/proc/*/"):
        pid = d.split("/")[2]
        if not pid.isdigit():
            continue
        try:
            comm = open(d + "comm").read().strip()
            if "QtWebEngine" not in comm:
                continue
            cl = open(d + "cmdline").read().replace("\x00", " ")
            m = re.search(r"--type=(\S+)", cl)
            typ = m.group(1) if m else "browser"
            rss = 0
            for ln in open(d + "status"):
                if ln.startswith("VmRSS"):
                    rss = int(ln.split()[1])
            out[pid] = (typ, rss)
        except OSError:
            pass
    return out


def renderer_rss_mb():
    procs = qtwebengine_processes()
    rend = [rss for (typ, rss) in procs.values() if typ == "renderer"]
    return (max(rend) // 1024) if rend else 0


# --------------------------------------------------------------------------- #
# Read-only capture snippets
# --------------------------------------------------------------------------- #
_RAF_CAPTURE = r"""
new Promise(res => {
  const orig = window.requestAnimationFrame.bind(window);
  const stacks = {};
  window.requestAnimationFrame = function (cb) {
    try {
      const st = (new Error().stack || '').split('\n').slice(2, 5).map(s => s.trim()).join(' <- ');
      stacks[st] = (stacks[st] || 0) + 1;
    } catch (e) {}
    return orig(cb);
  };
  setTimeout(() => {
    window.requestAnimationFrame = orig;  // restore — read-only overall
    res(Object.entries(stacks).sort((a, b) => b[1] - a[1]).slice(0, 10));
  }, %d);
});
"""

_MUTATION_CAPTURE = r"""
new Promise(res => {
  const counts = {};
  const mo = new MutationObserver(muts => {
    for (const m of muts) {
      const t = m.target;
      const key = m.type + ' ' + (t.id ? '#' + t.id
        : (t.className && t.className.toString ? '.' + t.className.toString().split(' ')[0] : t.nodeName));
      counts[key] = (counts[key] || 0) + 1;
    }
  });
  mo.observe(document.body, {subtree: true, childList: true, attributes: true, characterData: true});
  setTimeout(() => { mo.disconnect(); res(Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 12)); }, %d);
});
"""

_ANIMATIONS = r"""
JSON.stringify(document.getAnimations().filter(a => a.playState === 'running').map(a => {
  const e = a.effect && a.effect.target;
  return {name: a.animationName || '?',
          el: e ? (e.id || (e.className && e.className.toString ? e.className.toString().split(' ')[0] : e.nodeName)) : '?',
          visible: e ? (e.offsetParent !== null) : null};
}))
"""


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def cmd_counters(cdp, args):
    procs = qtwebengine_processes()
    print("QtWebEngine processes (RSS MB):")
    for pid, (typ, rss) in sorted(procs.items(), key=lambda kv: -kv[1][1]):
        print(f"  {pid:>7} {typ:<16} {rss // 1024:>7}")
    dc = cdp.call("Memory.getDOMCounters")
    print(f"\nDOM counters: nodes={dc.get('nodes')} documents={dc.get('documents')} "
          f"jsEventListeners={dc.get('jsEventListeners')}")
    heap = cdp.ev("(()=>{const m=performance.memory;return m?{used:Math.round(m.usedJSHeapSize/1048576),"
                  "total:Math.round(m.totalJSHeapSize/1048576),limit:Math.round(m.jsHeapSizeLimit/1048576)}:null})()")
    print(f"JS heap (MB): {heap}")
    live = cdp.ev("document.getElementsByTagName('*').length")
    print(f"live main-document nodes: {live}  (detached/other ≈ {dc.get('nodes', 0) - (live or 0)})")


_CHATDOM = """
(() => {
  const b = document.getElementById('chat-history');
  if (!b) return null;
  return {children: b.children.length,
          fromBottom: Math.round(b.scrollHeight - b.scrollTop - b.clientHeight)};
})()
"""


def cmd_chatdom(cdp, args):
    duration = getattr(args, "duration", None) or 0
    end = time.time() + duration
    while True:
        st = cdp.ev(_CHATDOM)
        if st is None:
            print("no #chat-history element (is a chat session open?)")
            return
        print(f"chat-history children: {st['children']:>4}   "
              f"px from bottom: {st['fromBottom']}")
        if time.time() >= end:
            return
        time.sleep(1)


def cmd_slope(cdp, args):
    r0 = renderer_rss_mb()
    n0 = cdp.call("Memory.getDOMCounters").get("nodes")
    time.sleep(args.duration)
    r1 = renderer_rss_mb()
    n1 = cdp.call("Memory.getDOMCounters").get("nodes")
    d = args.duration
    print(f"renderer RSS: {r0} -> {r1} MB  ({(r1 - r0) / d:+.2f} MB/s)")
    if n0 is not None and n1 is not None:
        print(f"DOM nodes:    {n0} -> {n1}      ({(n1 - n0) / d:+.0f} nodes/s)")


def cmd_animations(cdp, args):
    raw = cdp.ev(_ANIMATIONS)
    anims = json.loads(raw) if raw else []
    print(f"running CSS animations: {len(anims)}")
    for a in anims:
        vis = "visible" if a.get("visible") else "hidden"
        print(f"  {a['name']:<28} on {a['el']:<24} ({vis})")


def cmd_raf(cdp, args):
    print(f"capturing requestAnimationFrame schedulers for {args.duration}s ...")
    rows = cdp.ev(_RAF_CAPTURE % int(args.duration * 1000), await_promise=True) or []
    if not rows:
        print("  (no rAF scheduling — no JS animation loop running)")
    for stack, n in rows:
        print(f"  {n:>4}  {stack[:160]}")


def cmd_mutations(cdp, args):
    print(f"capturing DOM mutations for {args.duration}s ...")
    rows = cdp.ev(_MUTATION_CAPTURE % int(args.duration * 1000), await_promise=True) or []
    if not rows:
        print("  (no DOM mutations)")
    for key, n in rows:
        print(f"  {n:>4}  {key[:90]}")


def cmd_producers(cdp, args):
    cmd_slope(cdp, args)
    print()
    cmd_animations(cdp, args)
    print()
    cmd_raf(cdp, args)
    print()
    cmd_mutations(cdp, args)


def cmd_purge(cdp, args):
    before = renderer_rss_mb()
    cdp.call("Memory.forciblyPurgeJavaScriptMemory")
    time.sleep(2)
    after = renderer_rss_mb()
    print(f"forciblyPurgeJavaScriptMemory: RSS {before} -> {after} MB  (reclaimed {before - after} MB)")


def odysseus_processes():
    """Yield (pid, label, cmdline) for every process in the Odysseus stack.

    Matches the host wrapper, the QtWebEngine children (renderer/zygote/gpu), the
    uvicorn backend, and the built-in MCP servers. Read-only /proc scan; Linux only.
    """
    import re
    # Order matters: QtWebEngine children carry --application-name=qt_wrapper.py
    # in their cmdline, so they must be matched before the host pattern.
    matchers = [
        ("webengine", re.compile(r"QtWebEngineProcess")),
        ("backend",  re.compile(r"uvicorn app:app")),
        ("mcp",      re.compile(r"mcp_servers/(\w+)_server\.py")),
        ("host",     re.compile(r"qt_wrapper\.py|mac_wrapper\.py|windows_wrapper\.py")),
    ]
    for d in glob.glob("/proc/*/"):
        pid = d.split("/")[2]
        if not pid.isdigit():
            continue
        try:
            cl = open(d + "cmdline").read().replace("\x00", " ").strip()
        except OSError:
            continue
        if not cl:
            continue
        for kind, rx in matchers:
            m = rx.search(cl)
            if not m:
                continue
            if kind == "mcp":
                label = f"mcp:{m.group(1)}"
            elif kind == "webengine":
                tm = re.search(r"--type=(\S+)", cl)
                label = f"webengine:{tm.group(1) if tm else 'browser'}"
            else:
                label = kind
            yield pid, label, cl
            break


def _smaps_rollup(pid):
    """Return (rss, pss, private) in kB from /proc/<pid>/smaps_rollup, or None."""
    rss = pss = priv = 0
    try:
        for ln in open(f"/proc/{pid}/smaps_rollup"):
            f = ln.split()
            if ln.startswith("Rss:"):
                rss = int(f[1])
            elif ln.startswith("Pss:"):
                pss += int(f[1])
            elif ln.startswith(("Private_Clean:", "Private_Dirty:")):
                priv += int(f[1])
    except OSError:
        return None
    return rss, pss, priv


def cmd_eval(cdp, args):
    """Evaluate a read-only JS expression in the live page and print the value.

    Promises are awaited. Objects come back JSON-encoded (returnByValue).
    """
    val = cdp.ev(args.expression, await_promise=True)
    if isinstance(val, (dict, list)):
        print(json.dumps(val, indent=2))
    else:
        print(val)


def cmd_stack(cdp, args):
    """Per-process RSS / PSS / Private across the whole Odysseus stack.

    PSS splits shared copy-on-write pages fairly; Private is what you actually
    reclaim by stopping a process. RSS double-counts shared pages — compare the
    columns to see how much (e.g. the QtWebEngine zygotes are almost all shared).
    """
    rows = sorted(odysseus_processes(), key=lambda r: r[1])
    print(f"{'PID':>7}  {'LABEL':<20} {'RSS':>9} {'PSS':>9} {'PRIV':>9}  (kB)")
    print("-" * 70)
    t_rss = t_pss = t_priv = 0
    for pid, label, _cl in rows:
        m = _smaps_rollup(pid)
        if m is None:
            continue
        rss, pss, priv = m
        t_rss += rss; t_pss += pss; t_priv += priv
        print(f"{pid:>7}  {label:<20} {rss:>9} {pss:>9} {priv:>9}")
    print("-" * 70)
    print(f"{'':>7}  {'TOTAL':<20} {t_rss:>9} {t_pss:>9} {t_priv:>9}")
    print(f"\nStack PSS = {t_pss / 1024:.0f} MB   (what you'd reclaim ~ Private = "
          f"{t_priv / 1024:.0f} MB). PSS is the honest footprint number.")


def main():
    p = argparse.ArgumentParser(description="Read-only memory/CPU diagnostics for the Odysseus Qt wrapper.")
    p.add_argument("--port", type=int, default=9222, help="CDP port (default 9222)")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("counters", "animations", "purge", "stack"):
        sub.add_parser(name)
    for name in ("slope", "raf", "mutations", "producers"):
        sp = sub.add_parser(name)
        sp.add_argument("-d", "--duration", type=float, default=10.0, help="seconds (default 10)")
    sp = sub.add_parser("eval")
    sp.add_argument("expression", help="JS expression to evaluate in the page")
    sp = sub.add_parser("chatdom")
    sp.add_argument("-d", "--duration", type=float, default=0.0,
                    help="watch: one line per second for SECS (default: one-shot)")
    args = p.parse_args()

    # `stack` is a pure /proc reader — it needs no CDP connection, so it works
    # even when the remote-debugging port is closed.
    if args.cmd == "stack":
        cmd_stack(None, args)
        return

    cdp = CDP(port=args.port)
    try:
        {
            "counters": cmd_counters, "slope": cmd_slope, "animations": cmd_animations,
            "raf": cmd_raf, "mutations": cmd_mutations, "producers": cmd_producers, "purge": cmd_purge,
            "chatdom": cmd_chatdom, "eval": cmd_eval,
        }[args.cmd](cdp, args)
    finally:
        cdp.close()


if __name__ == "__main__":
    main()
