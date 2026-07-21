#!/usr/bin/env python3
"""Report what GPU/renderer a running Odysseus QtWebEngine is ACTUALLY using.

The wrappers decide GPU flags from a pre-launch probe (ioreg/devfs/EnumDisplay),
which predicts the rendering path but does not confirm it. This tool asks the
live browser: it queries Chrome DevTools `SystemInfo.getInfo` on the wrapper's
remote-debugging port and reports the compositing path, the GL renderer, and
whether it fell back to software (SwiftShader / llvmpipe / ANGLE software /
Microsoft Basic). Use it to verify hardware vs software rendering and which GPU
the GPU process bound to.

    python tooling/gpu_probe.py                 # localhost:9222
    python tooling/gpu_probe.py --host localhost --port 9222
    python tooling/gpu_probe.py --json          # machine-readable

`summarize_gpu` is a pure function so it is unit-tested without a live browser
(tests/test_gpu_probe.py); only `_fetch_system_info` touches the network.
"""
import argparse
import base64
import json
import os
import socket
import struct
import sys
import urllib.request

# Renderer/compositing substrings that mean "not on a real GPU".
_SOFTWARE_MARKERS = (
    "swiftshader", "llvmpipe", "softpipe", "software",
    "angle (apple software", "microsoft basic",
)


def summarize_gpu(info: dict) -> dict:
    """Reduce a CDP SystemInfo.getInfo result to a rendering summary.

    Pure: takes the parsed CDP payload, returns a dict with the renderer, vendor,
    device strings, the gpu_compositing/rasterization feature status, and a
    `software` boolean that is True when the effective path is CPU emulation.
    """
    gpu = (info or {}).get("gpu", {}) or {}
    feature = gpu.get("featureStatus", {}) or {}
    aux = gpu.get("auxAttributes", {}) or {}
    renderer = aux.get("glRenderer") or ""
    vendor = aux.get("glVendor") or ""
    devices = [d.get("deviceString", "") for d in gpu.get("devices", [])
               if d.get("deviceString")]
    gpu_compositing = feature.get("gpu_compositing", "unknown")

    # Software unless we positively see a real GL renderer whose name is not a
    # known CPU emulator and whose compositing is not disabled. A blank renderer
    # means GL never came up, so assume the worst rather than report "hardware".
    comp = str(gpu_compositing).lower()
    software = (
        not renderer.strip()
        or any(m in renderer.lower() for m in _SOFTWARE_MARKERS)
        or "software" in comp
        or "disabled" in comp
    )
    return {
        "renderer": renderer,
        "vendor": vendor,
        "devices": devices,
        "gpu_compositing": gpu_compositing,
        "rasterization": feature.get("rasterization", "unknown"),
        "software": software,
        "feature_status": feature,
    }


def format_summary(summary: dict) -> str:
    """Human-readable one-screen report of a summarize_gpu() result."""
    verdict = "SOFTWARE (CPU emulation)" if summary["software"] else "HARDWARE"
    lines = [
        f"rendering       : {verdict}",
        f"gl renderer     : {summary['renderer'] or '(none)'}",
        f"gl vendor       : {summary['vendor'] or '(none)'}",
        f"gpu_compositing : {summary['gpu_compositing']}",
        f"rasterization   : {summary['rasterization']}",
    ]
    if summary["devices"]:
        lines.append("devices         : " + "; ".join(summary["devices"]))
    return "\n".join(lines)


def _fetch_system_info(host: str, port: int, timeout: float = 5.0) -> dict:
    """CDP SystemInfo.getInfo over the browser target, via stdlib only.

    Mirrors the wrappers' one-shot _cdp_ws_call primitive: the browser target's
    WebSocket URL is at /json/version (not /json, which lists page targets).
    """
    ver = json.load(urllib.request.urlopen(
        f"http://{host}:{port}/json/version", timeout=timeout))
    ws_url = ver["webSocketDebuggerUrl"]
    path = ws_url.split(f":{port}", 1)[1]
    key = base64.b64encode(os.urandom(16)).decode()
    sock = socket.create_connection((host, port), timeout=timeout)
    try:
        sock.sendall(
            f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\n"
            f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n\r\n".encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += sock.recv(4096)

        payload = json.dumps({"id": 1, "method": "SystemInfo.getInfo"}).encode()
        mask = os.urandom(4)
        header = b"\x81"
        n = len(payload)
        if n < 126:
            header += bytes([0x80 | n])
        elif n < 65536:
            header += bytes([0xFE]) + struct.pack(">H", n)
        else:
            header += bytes([0xFF]) + struct.pack(">Q", n)
        sock.sendall(header + mask
                     + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

        def _read(n):
            out = b""
            while len(out) < n:
                out += sock.recv(n - len(out))
            return out

        while True:
            b1, b2 = _read(2)
            length = b2 & 0x7F
            if length == 126:
                length = struct.unpack(">H", _read(2))[0]
            elif length == 127:
                length = struct.unpack(">Q", _read(8))[0]
            msg = json.loads(_read(length))
            if msg.get("id") == 1:
                return msg.get("result", {})
    finally:
        sock.close()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=9222)
    ap.add_argument("--json", action="store_true", help="emit the summary as JSON")
    args = ap.parse_args(argv)

    try:
        info = _fetch_system_info(args.host, args.port)
    except Exception as e:
        print(f"gpu_probe: could not reach CDP at {args.host}:{args.port} "
              f"(is the wrapper running with --remote-debugging-port?): {e!r}",
              file=sys.stderr)
        return 2

    summary = summarize_gpu(info)
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(format_summary(summary))
    # Exit 1 when software-rendering, so scripts/CI can gate on it.
    return 1 if summary["software"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
