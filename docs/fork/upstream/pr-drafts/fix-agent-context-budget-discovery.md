# PR Draft: fix/agent-context-budget-discovery → odysseus-dev/odysseus:dev

**Branch:** `fix/agent-context-budget-discovery`
**Issue:** [#54](https://github.com/jdmanring/odysseus/issues/54) (fork tracking)
**Status:** Ready to file

---

## Title

`fix(model-context): probe context length for api/proxy endpoints instead of skipping`

---

## Summary

### Problem

`_query_context_length` has an early-return for `endpoint_kind in ("api", "proxy")` that
skips the network probe entirely and falls back to the `KNOWN_CONTEXT_WINDOWS` static
table. When a model is not in the table, `known=False`, causing `budget_context_for_model`
to return `0`, which disables auto-scaling and locks `agent_input_token_budget` at its
6000-token sentinel — effectively dropping 85% of agent context on every call.

The original intent was to avoid downloading full model catalogs on remote endpoints.
That concern is addressed by the existing `(endpoint_url, model)` cache: the probe runs
at most once per model per server lifetime. Keeping the early-return means every frontier
model released after the last table update silently degrades to 5K context.

Confirmed in production logs: 203 trim events, average 57,325 tokens accumulated at trim
time, average 49,124 tokens dropped per call (85.6%).

### Fix

Remove the early-return block:

```python
# Before
if configured_kind in ("api", "proxy"):
    if known:
        return known, True
    return DEFAULT_CONTEXT, False
```

Replace with priority-order resolution after the probe runs:

```python
# After (probe runs for all endpoint kinds)
if api_ctx and known:
    return max(api_ctx, known), True   # trust the larger of the two
if api_ctx:
    return api_ctx, True
if known:
    return known, True
return DEFAULT_CONTEXT, False
```

The probe result (`api_ctx`) comes from the `/v1/models` endpoint's `context_length`
field. For endpoints that don't return this field (including NVIDIA NIM), `api_ctx` is
`None` and the table value is used as before — so this change is a no-op for NIM
specifically. For endpoints that do return `context_length`, models are now auto-
discovered without any table entry required.

### Testing

- `tests/test_model_context.py` — updated `test_configured_proxy_uses_default_without_model_listing`:
  the probe now runs for proxy endpoints (one `/v1/models` call), but when the probe
  returns no models the result is still `DEFAULT_CONTEXT`. New tests: probe runs for
  api/proxy, result is cached after first call, known model still returns table value
  when probe returns nothing.

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

1. Configure any OpenAI-compatible API endpoint (e.g. together.ai, fireworks.ai) that
   does return `context_length` in its `/v1/models` response.
2. Set a model that is NOT in `KNOWN_CONTEXT_WINDOWS` as the active model.
3. Start an agent session. Confirm the log shows `known=True` and the budget auto-scales
   to ~85% of the model's actual context rather than defaulting to 6000.
4. Confirm the same call is not repeated on the second request (cache is effective).
5. For NVIDIA NIM (which does not return context_length): confirm existing behaviour is
   unchanged — table lookup still works and no regression in recognized models.
6. Run `pytest tests/test_model_context.py -q`.

---

## Filing Notes

- One commit. No squash needed.
- Branch: `fix/agent-context-budget-discovery` — built from `upstream-mirror`.
- **File upstream issue first.** Add the upstream issue number to `Fixes #` above.
- Related: the companion table-expansion in `feat/nvidia-nim-support` (#56) covers the
  NIM-specific case where the probe returns nothing. These can be filed independently.

## Visual / UI changes

None.
