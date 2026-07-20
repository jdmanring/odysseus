"""Behavioral integration test for the undo-snapshot gzip codec (jdmanring#99).

Exercises the EXACT round-trip the editor's _compressSnap/_decompressSnap use —
getImageData -> gzip -> gunzip -> new ImageData -> putImageData -> getImageData —
in a real browser, and asserts the pixels are byte-identical. This is the
correctness property that motivated gzip over PNG (PNG via canvas premultiplies
alpha and drifts partial-alpha pixels).

Does NOT cover the editor's async undo/redo orchestration (race guard, idle
scheduling, crop-undo) — that needs a live editor UI smoke-test.

Requires the Qt wrapper's CDP endpoint on localhost:9222; skips cleanly otherwise.
"""
import base64
import http.client
import json
import os
import socket
import struct

import pytest

CDP_HOST, CDP_PORT = "localhost", 9222


def _cdp_up():
    try:
        c = http.client.HTTPConnection(CDP_HOST, CDP_PORT, timeout=1)
        c.request("GET", "/json")
        ok = c.getresponse().status == 200
        c.close()
        return ok
    except Exception:
        return False


# Opt-in ONLY: this test drives the USER'S LIVE SESSION via CDP (it types into
# the editor). Same policy as test_idle_gc_integration — never auto-run just
# because the app happens to be open.
pytestmark = pytest.mark.skipif(
    os.environ.get("ODYSSEUS_LIVE_UI_TESTS") != "1" or not _cdp_up(),
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


def _connect():
    url = _ws_url()
    hp = url[len("ws://"):]
    host = hp.split("/", 1)[0].split(":")[0]
    path = "/" + hp.split("/", 1)[1]
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
    hdr = bytes([0x81]) + (bytes([0x80 | n]) if n < 126 else bytes([0x80 | 126, n >> 8, n & 0xFF])) + mask
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


def _eval(s, expr, _id=[0]):
    _id[0] += 1
    _send(s, {"id": _id[0], "method": "Runtime.evaluate",
              "params": {"expression": expr, "awaitPromise": True, "returnByValue": True}})
    while True:
        m = _recv(s)
        if m.get("id") == _id[0]:
            return m.get("result", {}).get("result", {}).get("value")


_JS = r"""
(async () => {
  function gz(u8){ const cs=new CompressionStream('gzip'); const w=cs.writable.getWriter(); w.write(u8); w.close();
    return new Response(cs.readable).arrayBuffer().then(a=>new Uint8Array(a)); }
  function gunz(u8){ const ds=new DecompressionStream('gzip'); const w=ds.writable.getWriter(); w.write(u8); w.close();
    return new Response(ds.readable).arrayBuffer().then(a=>new Uint8ClampedArray(a)); }
  async function roundtrip(fill){
    const W=512,H=512;
    const c=document.createElement('canvas'); c.width=W; c.height=H;
    const ctx=c.getContext('2d');
    const id1=ctx.createImageData(W,H); fill(id1.data, W, H);
    ctx.putImageData(id1,0,0);
    const captured=ctx.getImageData(0,0,W,H);
    const bytes=await gunz(await gz(captured.data));
    const id2=new ImageData(bytes, W, H);
    const c2=document.createElement('canvas'); c2.width=W; c2.height=H;
    const ctx2=c2.getContext('2d'); ctx2.putImageData(id2,0,0);
    const restored=ctx2.getImageData(0,0,W,H);
    if(restored.data.length!==captured.data.length) return false;
    for(let i=0;i<captured.data.length;i++) if(restored.data[i]!==captured.data[i]) return false;
    return true;
  }
  const noise = await roundtrip((d)=>{ for(let i=0;i<d.length;i++) d[i]=(Math.random()*256)|0; });
  const alpha = await roundtrip((d,W,H)=>{ for(let p=0;p<W*H;p++){ const i=p*4; d[i]=224;d[i+1]=108;d[i+2]=117; d[i+3]=(p%256); } });
  const layer = await roundtrip((d,W,H)=>{ for(let p=0;p<W*H;p++){ const i=p*4; const on=(p%7===0); d[i]=30;d[i+1]=30;d[i+2]=46;d[i+3]=on?200:0; } });
  return JSON.stringify({ hasCS: typeof CompressionStream==='function', noise, alpha, layer });
})()
"""


def test_gzip_codec_roundtrip_is_lossless():
    s = _connect()
    try:
        res = json.loads(_eval(s, _JS))
    finally:
        s.close()
    assert res["hasCS"], "CompressionStream must be available in the runtime"
    # Byte-exact restore for all three cases — including partial-alpha, which a
    # PNG/canvas round-trip would drift (premultiplied alpha).
    assert res["noise"], "photo-noise round-trip not byte-exact"
    assert res["alpha"], "partial-alpha round-trip not byte-exact (PNG-premultiply class bug)"
    assert res["layer"], "transparent-layer round-trip not byte-exact"
