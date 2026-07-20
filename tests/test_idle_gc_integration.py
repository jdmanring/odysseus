"""Behavioral integration test for the idle-triggered GC (chat.js _scheduleIdleGc).

Unlike the source-text guards in test_chat_gc_hint_js.py (which assert the code
*exists*), this test asserts the idle GC *works*: it grows the renderer's DOM
node count by hover-storming the Brain memory list, then sits fully idle (no
input, no chat) and verifies the node count is reclaimed within the idle window
— with no manual gc() call.

Requires a running Qt wrapper exposing CDP on localhost:9222 (which also implies
--expose-gc). Skips cleanly when that endpoint is absent, so normal/CI runs are
unaffected. Run locally with the app open:  venv/bin/python -m pytest \
    tests/test_idle_gc_integration.py -v
"""
import base64
import http.client
import json
import os
import socket
import struct
import time

import pytest

CDP_HOST, CDP_PORT = "localhost", 9222


def _cdp_available():
    try:
        c = http.client.HTTPConnection(CDP_HOST, CDP_PORT, timeout=1)
        c.request("GET", "/json")
        ok = c.getresponse().status == 200
        c.close()
        return ok
    except Exception:
        return False


# Opt-in ONLY: this test drives the USER'S LIVE SESSION — it opens the Brain
# panel and hover-storms the memory list. Auto-running it whenever the app
# happens to be open hijacks whatever the user is doing (observed live: the
# Brain menu opening under the user mid-session during a full-suite run).
pytestmark = pytest.mark.skipif(
    os.environ.get("ODYSSEUS_LIVE_UI_TESTS") != "1" or not _cdp_available(),
    reason="live-session test: set ODYSSEUS_LIVE_UI_TESTS=1 with the app open to run",
)


def _ws_url():
    c = http.client.HTTPConnection(CDP_HOST, CDP_PORT, timeout=5)
    c.request("GET", "/json")
    data = json.loads(c.getresponse().read())
    c.close()
    for t in data:
        if t.get("type") == "page":
            return t["webSocketDebuggerUrl"]
    raise RuntimeError("no page target")


def _handshake(host, path):
    s = socket.create_connection((host, CDP_PORT), timeout=10)
    key = base64.b64encode(os.urandom(16)).decode()
    s.sendall(
        f"GET {path} HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\n"
        f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
        f"Sec-WebSocket-Version: 13\r\n\r\n".encode()
    )
    buf = b""
    while b"\r\n\r\n" not in buf:
        buf += s.recv(4096)
    return s


def _send(s, msg):
    d = json.dumps(msg).encode()
    n = len(d)
    mask = os.urandom(4)
    hdr = bytes([0x81]) + (
        bytes([0x80 | n]) if n < 126 else bytes([0x80 | 126, n >> 8, n & 0xFF])
    ) + mask
    s.sendall(hdr + bytes(b ^ mask[i % 4] for i, b in enumerate(d)))


def _recv(s):
    def rb(n):
        b = b""
        while len(b) < n:
            ch = s.recv(n - len(b))
            if not ch:
                raise ConnectionError("closed")
            b += ch
        return b

    h = rb(2)
    ln = h[1] & 0x7F
    if ln == 126:
        ln = struct.unpack(">H", rb(2))[0]
    elif ln == 127:
        ln = struct.unpack(">Q", rb(8))[0]
    return json.loads(rb(ln))


class _CDP:
    def __init__(self):
        url = _ws_url()
        hp = url[len("ws://"):]
        host = hp.split("/", 1)[0].split(":")[0]
        path = "/" + hp.split("/", 1)[1]
        self.s = _handshake(host, path)
        self._id = 0

    def call(self, method, params=None):
        self._id += 1
        _send(self.s, {"id": self._id, "method": method, "params": params or {}})
        while True:
            m = _recv(self.s)
            if m.get("id") == self._id:
                return m.get("result", {})

    def eval(self, expr, by_value=True):
        return self.call(
            "Runtime.evaluate", {"expression": expr, "returnByValue": by_value}
        ).get("result", {}).get("value")

    def nodes(self):
        return self.call("Memory.getDOMCounters").get("nodes", 0)

    def close(self):
        try:
            self.s.close()
        except Exception:
            pass


def test_idle_gc_reclaims_hover_churn():
    cdp = _CDP()
    try:
        # --expose-gc must be on for the idle GC to do anything.
        if not cdp.eval("typeof gc === 'function'"):
            pytest.skip("gc() not exposed (wrapper not launched with --expose-gc)")

        # Open the Brain memory panel and collect on-screen item centres.
        cdp.eval("document.querySelector('#tool-memory-btn')?.click(); void 0")
        time.sleep(1.0)
        pts = json.loads(cdp.eval(
            "JSON.stringify(Array.from(document.querySelectorAll('.memory-item'))"
            ".map(e=>{var r=e.getBoundingClientRect();"
            "return [Math.round(r.left+r.width/2),Math.round(r.top+r.height/2)];})"
            ".filter(p=>p[1]>0&&p[1]<980))"
        ) or "[]")
        if len(pts) < 3:
            pytest.skip("Brain memory list not populated enough to stress")

        # Clean baseline.
        cdp.eval("gc(); void 0")
        time.sleep(0.8)
        base = cdp.nodes()

        # Grow the node count by moving the real cursor over the items (CSS
        # :hover pseudo-elements are created/destroyed → transient DOM churn).
        for k in range(1200):
            x, y = pts[k % len(pts)]
            cdp.call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
        peak = cdp.nodes()
        growth = peak - base
        assert growth > 200, (
            f"hover did not grow the node count enough to test "
            f"(base={base}, peak={peak}, growth={growth})"
        )

        # Sit fully idle — no input, no chat. The idle GC (_IDLE_GC_MS ≈ 8s)
        # must fire on its own and reclaim the churn. Poll up to ~18s.
        final = peak
        deadline = time.time() + 18
        while time.time() < deadline:
            time.sleep(2)
            final = cdp.nodes()
            if final - base < growth * 0.5:
                break

        reclaimed = peak - final
        assert final - base < growth * 0.5, (
            "idle GC did not reclaim the hover churn while idle "
            f"(base={base}, peak={peak}, final={final}, reclaimed={reclaimed}). "
            "Expected the node count to fall at least halfway back to baseline "
            "with no chat activity."
        )
    finally:
        cdp.close()
