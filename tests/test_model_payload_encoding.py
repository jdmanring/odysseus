"""Payloads serialized into the model's context are encoded compactly.

Three formatters serialize a structure, feed it to the model, and truncate it
at a character cap. Indentation whitespace spent against that cap displaces
real data: measured on a 40-event calendar payload, pretty-printing alone took
it from 6937 to 9905 characters and pushed it past `format_tool_result`'s 8000
cap, so the events were cut off mid-object.

These tests assert on the *emitted string*, not on source text, so they fail if
a formatter goes back to `indent=` however that is spelled.
"""
import json

import pytest

from src.tool_execution import format_tool_result


def _uniform_events(n):
    return [
        {"id": f"evt-{i:04d}", "title": f"Event {i}",
         "start": f"2026-08-{(i % 28) + 1:02d}T09:00:00",
         "end": f"2026-08-{(i % 28) + 1:02d}T10:00:00",
         "event_type": "work", "importance": "normal",
         "all_day": False, "location": "Zoom"}
        for i in range(n)
    ]


def _json_block(text):
    """The ```json fenced block format_tool_result emits, or None."""
    marker = "```json\n"
    if marker not in text:
        return None
    return text.split(marker, 1)[1].rsplit("\n```", 1)[0]


# --- the encoding itself ------------------------------------------------------

def test_tool_result_payload_is_not_pretty_printed():
    out = format_tool_result("calendar", {"response": "ok", "events": _uniform_events(3)})
    block = _json_block(out)
    assert block is not None, "no json block emitted"
    # A pretty-printed payload puts a newline after '{'; a compact one never does.
    assert "\n" not in block, f"payload is pretty-printed:\n{block[:200]}"
    assert ": " not in block and ", " not in block, "separators are not compact"


def test_tool_result_payload_still_round_trips():
    """Compact is an encoding change, not a data change."""
    payload = {"events": _uniform_events(5), "count": 5, "nested": {"a": [1, 2, {"b": None}]}}
    out = format_tool_result("calendar", {"response": "ok", **payload})
    assert json.loads(_json_block(out)) == payload


def test_unicode_is_still_not_escaped():
    """ensure_ascii=False must survive: escaping doubles the cost of non-ASCII."""
    out = format_tool_result("notes", {"response": "ok", "notes": [{"t": "café — 日本語"}]})
    assert "café" in out and "日本語" in out
    assert "\\u" not in _json_block(out)


# --- the reason it matters: the cap ------------------------------------------

def test_a_realistic_payload_no_longer_truncates():
    """40 events fit under the 8000-char cap compactly, and did not pretty."""
    events = _uniform_events(40)
    pretty = json.dumps({"events": events}, indent=2, default=str, ensure_ascii=False)
    compact = json.dumps({"events": events}, separators=(",", ":"),
                         default=str, ensure_ascii=False)
    assert len(pretty) > 8000, "fixture no longer demonstrates the bug; enlarge it"
    assert len(compact) < 8000, "fixture no longer fits; the cap or shape changed"

    out = format_tool_result("calendar", {"response": "ok", "events": events})
    assert "truncated" not in out, "payload truncated despite fitting compactly"
    assert json.loads(_json_block(out)) == {"events": events}


def test_oversized_payloads_are_still_capped():
    """The cap must still apply; this is an encoding fix, not a cap removal."""
    out = format_tool_result("calendar", {"response": "ok", "events": _uniform_events(2000)})
    assert "truncated" in out
    assert len(out) < 20000


# --- the sibling formatters ---------------------------------------------------

def _run_execute_api_call(monkeypatch, payload):
    """Drive the real execute_api_call with a stubbed HTTP response."""
    import asyncio

    import httpx

    from src import integrations

    monkeypatch.setattr(integrations, "_find_integration",
                        lambda _id: {"name": "t", "enabled": True,
                                     "base_url": "https://example.invalid"},
                        raising=False)
    # The SSRF guard resolves the host before any request is made; stub it so
    # the test exercises the formatter rather than DNS.
    import src.url_safety
    monkeypatch.setattr(src.url_safety, "check_outbound_url",
                        lambda *a, **k: (True, ""), raising=False)

    class _Resp:
        status_code = 200
        headers = {"content-type": "application/json"}
        text = ""

        def json(self):
            return payload

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def request(self, *a, **k):
            return _Resp()

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    return asyncio.run(integrations.execute_api_call("t", "GET", "/x"))


def test_integration_response_is_compact(monkeypatch):
    """The real execute_api_call, not a re-implementation of its formatting."""
    result = _run_execute_api_call(monkeypatch, {"items": _uniform_events(3)})
    assert "error" not in result, f"harness never reached the formatter: {result}"
    body = "".join(str(v) for v in result.values())
    assert "evt-0000" in body, "payload absent; the harness is not exercising the format path"
    assert "\n  " not in body, f"integration response is pretty-printed: {body[:200]}"


def test_integration_truncation_keeps_more_items_when_compact(monkeypatch):
    """The binary search must measure the encoding it emits.

    If one of the five json.dumps calls in that block kept indent=2 while the
    others went compact, the fit calculation would be computed against a
    different string than the one emitted.
    """
    result = _run_execute_api_call(monkeypatch, _uniform_events(400))
    assert "error" not in result, f"harness never reached the formatter: {result}"
    text = "".join(str(v) for v in result.values())
    assert "_truncated" in text, "400 events should exceed the 12000-char cap"
    assert "shown_items" in text
    # `output` is "HTTP <status>\n" followed by the formatted body.
    body = result["output"].split("\n", 1)[1]
    parsed = json.loads(body)
    assert isinstance(parsed, list) and parsed[-1]["_truncated"] is True
    assert parsed[-1]["shown_items"] == len(parsed) - 1

    # The two halves of the mismatch, which parsing alone does NOT catch --
    # a pretty-printed emit still parses and still reports the right count.
    #
    # Emit pretty while measuring compact -> the body blows past the cap.
    assert len(body) <= 12000, (
        f"emitted {len(body)} chars against a 12000 cap: the encoding used to "
        "measure the fit is not the encoding being emitted"
    )
    # Measure pretty while emitting compact -> the body under-fills badly,
    # wasting the budget the fix exists to reclaim. Measured on this fixture:
    # correct 11845 chars / 69 items; with the binary search left on indent=2,
    # 9109 chars / ~53 items. 11000 separates them with room for fixture drift.
    # (A first attempt used 9000 and the mutant slipped through by 109 chars --
    # the bound has to come from both measurements, not from one.)
    assert len(body) > 11000, (
        f"emitted only {len(body)} chars of a 12000 budget: the fit is being "
        "measured against a more verbose encoding than the one emitted"
    )


def test_no_model_facing_formatter_reintroduces_indentation():
    """Behavioural sweep: every formatter under test emits compact JSON.

    Deliberately not a source grep for `indent=`. A source assertion passes
    when the literal survives in a comment or an uncalled branch, which is how
    a guard in this repo was defeated before.
    """
    samples = [
        {"response": "ok", "events": _uniform_events(2)},
        {"response": "ok", "tasks": [{"id": 1, "title": "x", "done": False}]},
        {"response": "ok", "notes": [{"id": "n1", "body": "hello"}]},
    ]
    for s in samples:
        block = _json_block(format_tool_result("t", s))
        assert block is not None and "\n" not in block, f"pretty-printed: {s.keys()}"
