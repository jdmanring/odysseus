"""Minimal OpenAI-compatible mock model server for end-to-end streaming tests.

The app treats any unrecognized host as an OpenAI-compatible endpoint, so a
local server speaking POST /v1/chat/completions (SSE) lets the REAL app run a
REAL multi-exchange streaming session in a headless browser — no GPU, no live
model. Pair with live_app.seed_endpoint() so the endpoint passes the session/
endpoint match validation in chat_routes.

Behavior knobs are constructor args, not globals, so a suite can run several
personalities (slow first token to exercise the thinking indicator, long
replies to exercise streaming layout) against one server lifetime.
"""
import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODEL_ID = "mock-model"

# When the last user message carries this marker, the reply ends with
# "ACK <marker>." — a deterministic per-exchange completion signal a browser
# test can wait for (DOM text alone can't distinguish reply N from N-1).
_MARKER_RE = re.compile(r"SOAKMSG \d+")


class MockLLM:
    """OpenAI-compatible /v1 server. `reply_tokens` strings are streamed as
    separate SSE deltas at `token_delay_s` cadence after `first_token_delay_s`
    (the window where the app shows its thinking indicator)."""

    def __init__(self, reply_tokens=None, first_token_delay_s=0.25,
                 token_delay_s=0.01, slow_first_n=None, mid_pause_s=None):
        """`slow_first_n`: apply `first_token_delay_s` (and `mid_pause_s`)
        only to the first N streaming requests; the rest answer near-instantly,
        so a soak stays fast. `mid_pause_s`: a single pause after the 4th
        token — the app shows its thinking overlay after a 400ms no-text gap
        mid-stream, so a pause >400ms exercises that path end to end."""
        self.reply_tokens = reply_tokens or (
            ["Reply "] + [f"token{i} " for i in range(24)] + ["END."])
        self.first_token_delay_s = first_token_delay_s
        self.token_delay_s = token_delay_s
        self.slow_first_n = slow_first_n
        self.mid_pause_s = mid_pause_s
        self.requests_served = 0
        self.streams_served = 0
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def do_GET(self):
                if self.path.rstrip("/").endswith("/models"):
                    body = json.dumps(
                        {"object": "list",
                         "data": [{"id": MODEL_ID, "object": "model"}]}
                    ).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.send_error(404)

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                try:
                    req = json.loads(self.rfile.read(length) or b"{}")
                except ValueError:
                    req = {}
                outer.requests_served += 1
                marker = None
                for msg in reversed(req.get("messages", [])):
                    if msg.get("role") == "user":
                        m = _MARKER_RE.search(str(msg.get("content", "")))
                        marker = m.group(0) if m else None
                        break
                tokens = list(outer.reply_tokens)
                if marker:
                    tokens.append(f" ACK {marker}.")
                if req.get("stream"):
                    self._stream(tokens)
                else:
                    self._complete(tokens)

            def _sse(self, obj):
                self.wfile.write(f"data: {json.dumps(obj)}\n\n".encode())
                self.wfile.flush()

            def _stream(self, tokens):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.end_headers()
                base = {"id": "mock-1", "object": "chat.completion.chunk",
                        "model": MODEL_ID}
                outer.streams_served += 1
                slow = (outer.slow_first_n is None
                        or outer.streams_served <= outer.slow_first_n)
                time.sleep(outer.first_token_delay_s if slow else 0.02)
                self._sse({**base, "choices": [
                    {"index": 0, "delta": {"role": "assistant"},
                     "finish_reason": None}]})
                for idx, tok in enumerate(tokens):
                    self._sse({**base, "choices": [
                        {"index": 0, "delta": {"content": tok},
                         "finish_reason": None}]})
                    if slow and outer.mid_pause_s and idx == 3:
                        time.sleep(outer.mid_pause_s)
                    else:
                        time.sleep(outer.token_delay_s)
                self._sse({**base, "choices": [
                    {"index": 0, "delta": {}, "finish_reason": "stop"}]})
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()

            def _complete(self, tokens):
                text = "".join(tokens)
                body = json.dumps({
                    "id": "mock-1", "object": "chat.completion",
                    "model": MODEL_ID,
                    "choices": [{"index": 0, "finish_reason": "stop",
                                 "message": {"role": "assistant",
                                             "content": text}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1,
                              "total_tokens": 2},
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever,
                                        daemon=True)
        self._thread.start()
        self.base_url = f"http://127.0.0.1:{self._server.server_address[1]}/v1"

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.stop()

    def stop(self):
        self._server.shutdown()
        self._server.server_close()
