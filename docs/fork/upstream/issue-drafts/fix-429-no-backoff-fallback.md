# Issue Draft: 429 rate-limit responses bypass retry/backoff and trigger immediate fallback chain traversal

## Summary

When a model endpoint returns HTTP 429 (rate-limited) during streaming, Odysseus treats it
identically to a hard failure — no retry, no backoff, no `Retry-After` header inspection — and
immediately advances to the next fallback candidate. For a user with a deep fallback chain, a
brief rate-limit burst burns through every configured fallback in under 1 second and may exhaust
all candidates before the rate limit window expires. The endpoint that issued the 429 has already
told the client exactly how long to wait; Odysseus ignores it.

---

## Reproduction

1. Configure a primary model on an endpoint that rate-limits (e.g. NVIDIA NIM free tier, OpenAI
   free tier) with two or more fallback models.
2. Send requests fast enough to trigger 429 from the primary.
3. Watch the fallback notification in the UI — it fires immediately on the first rate-limit
   response, not after the provider's stated retry window.
4. If all fallbacks are on the same endpoint, the entire chain fails in under 2 seconds with no
   useful output.

---

## Root Cause (traced through code and confirmed in logs)

### Streaming path — zero retries

`stream_llm` (`src/llm_core.py`) opens an HTTP stream and checks the status code at connection
time:

```python
async with client.stream('POST', target_url, json=payload, ...) as r:
    if r.status_code != 200:
        raw = (await r.aread()).decode(errors="replace")
        friendly = _format_upstream_error(r.status_code, raw, target_url)
        yield f'event: error\ndata: {json.dumps({"status": r.status_code, "text": friendly, ...})}\n\n'
        return
```

A 429 here returns immediately with an `event: error` chunk. There is no retry loop in the
streaming path — not for 429, not for 502, not for 503.

### Fallback — no inter-candidate delay

`stream_llm_with_fallback` (`src/llm_core.py`, line 2296) treats any pre-content `event: error`
as a signal to advance to the next candidate:

```python
async for chunk in stream_llm(url, model, messages, headers=headers, **kwargs):
    if chunk.startswith("event: error"):
        if not emitted and not is_last:
            last_error = chunk
            retried = True
            ...
            break          # ← immediately tries next candidate
        yield chunk
        continue
```

There is no `asyncio.sleep` between candidates. A 429 from candidate 0 causes candidate 1 to
fire at once, with no delay.

### Non-streaming path — fixed delay, still ignores Retry-After

`llm_call_async` (`src/llm_core.py`, line 1645) does have a retry loop for 429:

```python
if r.status_code in (429, 502, 503, 504) and attempt < max_retries:
    await asyncio.sleep(LLMConfig.RETRY_DELAY)   # 0.5s, always
    continue
```

`LLMConfig.RETRY_DELAY = 0.5` and `LLMConfig.MAX_RETRIES = 3`. This gives 3 attempts at 0.5s
fixed intervals before raising — a total of ~1 second of backoff. `Retry-After` is not read.
For a provider that sets `Retry-After: 60`, a 3-attempt sequence that takes 1 second still fails,
then falls back.

### Retry-After header never read

No code in any path reads or acts on the `Retry-After` header. This header is present in NVIDIA
NIM 429 responses and provides the exact wait duration needed to succeed without burning fallbacks.

---

## Evidence from production logs

From `logs/server.log`, request `cc5018fb8ec3` (memory extraction via `llm_call_async`):

```
2026-06-16T20:31:54.693758Z  HTTP 429 Too Many Requests
2026-06-16T20:31:54.750481Z  LLM async call failed in 0.04s (attempt 1): HTTP 429 NVIDIA rate-limited
2026-06-16T20:31:55.286105Z  HTTP 429 Too Many Requests
2026-06-16T20:31:55.286522Z  LLM async call failed in 0.03s (attempt 2): HTTP 429 NVIDIA rate-limited
2026-06-16T20:31:55.834757Z  HTTP 429 Too Many Requests
2026-06-16T20:31:55.835238Z  LLM async call failed in 0.05s (attempt 3): HTTP 429 NVIDIA rate-limited
2026-06-16T20:31:55.835384Z  LLM memory extraction failed; using fallback candidates: 429
```

This is the non-streaming path: 3 attempts at ~0.5s intervals (0.54s gap: 54.750 → 55.286,
0.55s gap: 55.286 → 55.834), then immediate fallback to next candidate.

Aggregate from two log rotation files:
- **2,241 × HTTP 429** from NVIDIA NIM
- **1,585 × HTTP 200** from NVIDIA NIM
- **58% rate-limit failure rate** on primary model endpoint
- 429s appear in dense bursts, consistent with a per-minute quota being hit and then exhausted

---

## Impact

- **Fallback chain drained on brief rate limits**: A transient 429 that Retry-After says would
  clear in 10 seconds causes the full fallback chain to fire in under 1 second. The user receives
  a response from the last-resort fallback model (or an error if all fail) rather than waiting
  briefly for the primary.
- **Wasted fallback quota**: Secondary and tertiary models are used unnecessarily when the primary
  would have been available seconds later.
- **Compound failure with context budget bug**: Fallback models receive a pre-trimmed 5K token
  history when the primary model is unlisted (see related issue). A 429 on the primary + fallback
  = rate-limited primary + lobotomized fallback answer.
- **Streaming path has no backoff at all**: The 0.5s fixed delay in `llm_call_async` is at least
  something. The streaming path — used for all agent and chat completions — has zero delay,
  meaning each 429 in the streaming path triggers the next candidate in under 50ms.

---

## Proposed Fix

### 1. Read and respect Retry-After in stream_llm

Before yielding the error and returning on a 429, extract `Retry-After` from the response
headers. If present, sleep for that duration (capped at a reasonable maximum, e.g. 30s) and
retry once before falling back:

```python
if r.status_code == 429:
    retry_after = _parse_retry_after(r.headers)
    if retry_after and retry_after <= MAX_429_WAIT:
        await asyncio.sleep(retry_after)
        # retry will happen on next iteration (requires converting stream_llm to a loop)
        ...
```

### 2. Add a configurable inter-candidate delay in stream_llm_with_fallback

When advancing to the next candidate after a 429, sleep briefly before firing. This prevents
exhausting the chain when all fallbacks are on the same rate-limited endpoint:

```python
if chunk.startswith("event: error"):
    if not emitted and not is_last:
        ...
        if _is_rate_limit_error(last_error):
            await asyncio.sleep(FALLBACK_RATE_LIMIT_DELAY)  # e.g. 1.0s default
        break
```

### 3. Treat 429 separately from hard failures in the fallback loop

Today `stream_llm_with_fallback` treats connection errors, 5xx, and 429 identically. A 429 means
"I'm alive, slow down" — not "I'm dead". The fallback logic should reflect this:
- Hard failures (connection error, 5xx): fall back immediately
- 429: retry after Retry-After or a fixed delay before falling back

### 4. Replace RETRY_DELAY with exponential backoff + Retry-After in llm_call_async

The current `asyncio.sleep(0.5)` fixed delay provides minimal benefit against a 60-second rate
limit window. Replace with exponential backoff (1s, 2s, 4s) that is overridden by `Retry-After`
when present.

---

## What NOT to change

- The `PROTECT_RECENT = 10` floor in `trim_for_context` — unrelated.
- The dead-host cooldown mechanism — that's for unreachable hosts, not rate limits. These are
  different failure modes and should remain separate.
- The 3-attempt retry in `llm_call_async` for 502/503 — those are transient server errors that
  benefit from immediate retry. 429 should be separated from them.

---

## Files

- `src/llm_core.py` — `stream_llm` (OpenAI path, ~line 2051), `stream_llm_with_fallback`
  (~line 2296), `llm_call_async` (~line 1645), `LLMConfig` class (~line 18)
