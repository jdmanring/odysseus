# PR Draft: fix/stream-429-backoff → odysseus-dev/odysseus:dev

**Branch:** `fix/stream-429-backoff`
**Issue:** [#55](https://github.com/jdmanring/odysseus/issues/55) (fork tracking)
**Status:** Ready to file

---

## Title

`fix(llm): respect Retry-After on 429 in streaming and async paths`

---

## Summary

### Problem

All three LLM call paths treat HTTP 429 as a permanent failure with no backoff:

- **`stream_llm`** (main OpenAI streaming path): on any non-200 status it immediately
  yields an `event: error` chunk and returns. Zero retries.
- **`stream_llm_with_fallback`**: advances to the next fallback candidate immediately on
  any pre-content error, including 429. No delay between candidates.
- **`llm_call_async`**: retries 3 times at a fixed 0.5s `LLMConfig.RETRY_DELAY`. The
  `Retry-After` header is never read.

In practice, under sustained 429 load, `stream_llm_with_fallback` cycles through all
fallback candidates simultaneously (they share the same endpoint and same rate limit),
fails all of them, and reports failure — without waiting the seconds the provider
specified would clear the limit. A single retry with the header-specified wait would
often succeed.

Confirmed in production: 2,241 consecutive 429 responses from a single NIM endpoint
over 11 minutes (58% failure rate). The `Retry-After` header was present on every
response.

### Fix

**New helper** `_parse_retry_after(value, *, default, cap=60.0) -> float`:
Parses the `Retry-After` header (seconds-integer or HTTP-date format), clamps to
`[0, cap]`, returns `default` on missing or malformed values.

**`stream_llm`**: wrap the `async with client.stream(...)` block in a one-retry loop.
On `status_code == 429` and first attempt, read `Retry-After`, `await asyncio.sleep`,
then retry. If the retry also gets 429, yield error and return as before.

**`llm_call_async`**: on 429, read `Retry-After` header from the response instead of
sleeping `LLMConfig.RETRY_DELAY`. Existing 3-attempt retry structure is preserved.

**`stream_llm_with_fallback`**: on detecting a 429 error chunk from a candidate, sleep
1 second before advancing to the next candidate. This prevents simultaneously
hammering all fallback candidates on the same rate-limited endpoint.

### Testing

- `tests/test_llm_core_429_backoff.py` — new tests covering:
  - `_parse_retry_after`: integer seconds, HTTP-date, missing, malformed, cap enforcement
  - `stream_llm`: one retry on 429, honour Retry-After delay, no second retry on repeated 429
  - `llm_call_async`: reads Retry-After instead of fixed RETRY_DELAY
  - `stream_llm_with_fallback`: 1s delay before advancing after 429

## Target branch

- [x] This PR targets **`dev`**, not `main`.

## Linked Issue

Fixes # <!-- [add upstream issue number before filing] -->

## Type of Change

- [x] Bug fix (non-breaking, fixes a confirmed issue)
- [ ] New feature (non-breaking, adds new behaviour)
- [ ] Breaking change (changes or removes existing behaviour)
- [ ] Refactor / cleanup (behaviour unchanged)
- [ ] Documentation only
- [ ] CI / tooling / configuration

## Checklist

- [x] I searched [open issues](https://github.com/odysseus-dev/odysseus/issues) and [open PRs](https://github.com/odysseus-dev/odysseus/pulls); this is not a duplicate.
- [x] This PR targets `dev`
- [x] My changes are limited to the scope described above; no unrelated refactors or whitespace changes mixed in.
- [ ] **I am not an LLM agent submitting a bulk PR.** I reviewed and tested this change personally before submitting.

### How to Test

1. Configure a NIM endpoint with a key that is close to or over the rate limit.
2. Send a request and observe that the server reads the `Retry-After` header and
   waits the indicated duration before retrying rather than returning an error
   immediately.
3. Confirm that the second attempt (after the wait) succeeds when the window has reset.
4. For `stream_llm_with_fallback`: configure a fallback chain with two models on the
   same rate-limited endpoint. Confirm there is a 1-second gap between candidate
   attempts (visible in server logs) rather than immediate simultaneous failure.
5. Run `pytest tests/test_llm_core_429_backoff.py -q`.

---

## Filing Notes

- One commit. No squash needed.
- Branch: `fix/stream-429-backoff` — built from `upstream-mirror`.
- **File upstream issue first.** Add the upstream issue number to `Fixes #` above.
- The `_parse_retry_after` helper is intentionally narrow: seconds-integer or HTTP-date
  only (RFC 7231 §7.1.3). The `delta-seconds` form covers the NVIDIA NIM case; the
  HTTP-date form handles OpenAI and other providers.

## Visual / UI changes

None.
