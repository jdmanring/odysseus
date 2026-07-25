# Issue: Research lazy context-length probe for api/proxy endpoints

**Type:** Research / Future enhancement
**Fork issue:** to be filed

---

## Background

`_query_context_length` in `src/model_context.py` contains an early-return for
`endpoint_kind in ("api", "proxy")` that skips the `/v1/models` probe entirely and
falls back to the `KNOWN_CONTEXT_WINDOWS` static table. The intent (upstream commit
`a2e691da`) was to avoid downloading large model catalogs from commercial proxy
endpoints at model-picker open time, where performance matters. This is a deliberate
upstream architectural decision.

The immediate consequence (models not in the table getting a 6K budget) is addressed
by the table expansion in `feat/nvidia-nim-support`. The early-return itself is correct
for model-picker use but creates a blind spot for the agent budget path: even for
providers that do return `context_length` in their `/v1/models` response, we never see
it on api/proxy endpoints.

## The lazy probe idea

Rather than running the probe at model-picker open time (expensive, affects UI
responsiveness), run it only when the agent loop first needs to know the context budget,
i.e., deferred to first actual use. This preserves the "don't slow down the model
picker" intent while giving the agent accurate context for providers that do report it.

This is NOT a simple change. It requires:

1. **Separating the probe trigger from model-picker load.** Currently, `get_context_length`
   is called from the model picker path AND the agent budget path via the same
   synchronous function. A lazy probe would need the agent budget path to be able to
   trigger an async network call that the model picker path never initiates.

2. **Understanding the cache contract.** The current cache keys on `(endpoint_url, model)`.
   A lazy probe would write to the same cache but from a different call site. Verify
   there is no race condition under concurrent agent sessions with the same endpoint.

3. **The manual refresh button.** There is already a "Refresh models" button in the
   Settings -> Endpoints panel that triggers a full `/v1/models` fetch and updates the
   cached list. Investigate whether that button also updates the context-length cache or
   only the model ID list. If it already writes to `_context_cache`, users have a
   functional workaround for any endpoint whose context isn't in the table.

## Research questions before building

1. **Which providers actually return `context_length` (or equivalent) in their
   `/v1/models` response?** The probe looks for these fields (in priority order):
   - Top-level: `context_length`, `context_window`, `max_model_len`, `max_context_length`, `max_seq_len`
   - Nested (`meta` / `model_extra`): `n_ctx`, `context_length`, `context_window`, `max_model_len`
   
   Known state as of 2026-06-19:
   - **NVIDIA NIM**: Does NOT return any context field, table only.
   - **Together.ai**: Returns `context_length` at top level (to verify).
   - **Fireworks.ai**: Returns `context_length` at top level (to verify).
   - **Groq**: Returns `context_window` (to verify field name matches our probe).
   - **vLLM**: Returns `max_model_len` at top level, our probe covers this.
   - **OpenAI**: Does NOT return context fields in `/v1/models`: table only.
   - **LM Studio**: Returns `context_length`: our probe covers this (local, not affected by early-return).
   
   Before building lazy probe infrastructure, verify which commercial api/proxy
   endpoints actually return usable data. If the answer is "very few," expanding the
   static table remains more valuable than the probe infrastructure.

2. **Does the current probe cover all field names in use?** Run a manual test against
   Together.ai and Fireworks.ai: `GET /v1/models` -> check raw JSON for field names
   -> verify they match what the probe reads. Add any missing field names to the probe.

3. **How does the manual refresh button interact with `_context_cache`?** Trace the
   refresh flow in `routes/model_routes.py`. If the refresh already populates the
   context cache, the user workaround is already adequate and the lazy probe is low
   priority.

## Do not build yet

Do not implement the lazy probe until:
- The provider survey in question 1 is complete.
- The manual-refresh/cache interaction in question 3 is understood.
- There is at least one commercial api/proxy provider confirmed to return context fields
  that the probe would capture but the table does not cover.

## Files

- `src/model_context.py`; `_query_context_length`, `_context_cache`, early-return block
- `routes/model_routes.py`; model refresh flow, manual refresh button handler
