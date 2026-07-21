# Upstream Issue Draft: feat-longcat-provider

**File on:** `odysseus-dev/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/feat-longcat-provider.md`
**Branch:** `feat/longcat-provider`
**Type:** Enhancement / Bug fix

---

## Title

`[Providers] LongCat: add logo, fix output truncation at 32K, exclude from stream_options`

---

## Body

**Install method:** Docker / manual Python

**OS / device:** Any

**Problem:**

LongCat (longcat.chat) is a supported provider in Odysseus but has three gaps:

1. **No logo.** The LongCat endpoint shows a generic placeholder icon in the model picker and provider list.

2. **Output truncated at 32K tokens.** `_PROVIDER_DEFAULT_MAX_OUTPUT` has no entry for `"longcat"`, so the default `max_tokens` cap applies. LongCat's API supports up to 131,072 output tokens ([LongCat API docs](https://longcat.chat/platform/docs/APIDocs.html)). The low default causes the model to cut off long outputs prematurely.

3. **`stream_options` rejected.** LongCat's API returns a 422 error when `stream_options: {include_usage: true}` is included in the request. It should be excluded from `stream_options` alongside `openrouter`, `groq`, and `longcat` in the existing exclusion list.

**Steps to reproduce:**

1. Add a LongCat endpoint and select a LongCat model.
2. Request a long structured output (e.g., "Write a 50,000 word story..."). Observe: the response stops at ~32K tokens without warning.
3. Enable streaming with usage stats. Observe: LongCat returns a 422 error.

**Expected:**

- LongCat shows its logo in the model picker.
- Output cap set to 131,072 tokens for LongCat endpoints.
- `stream_options` not sent to LongCat endpoints.

**Source:** LongCat API documentation at https://longcat.chat/platform/docs/APIDocs.html confirms 131,072 max output tokens and the streaming API format.

**Affected files:**
- `static/js/providers.js` (or equivalent) — logo entry
- `src/agent_loop.py` or provider config — `_PROVIDER_DEFAULT_MAX_OUTPUT`, `stream_options` exclusion list
