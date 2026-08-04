# PR Draft: fix/model-context-org-prefix -> odysseus-dev/odysseus:dev

**Branch:** `fix/model-context-org-prefix`
**Issue:** #173 (fork tracking, `docs/fork/issues/INDEX.md`)
**Status:** Ready to file
**Base:** cut from `upstream-mirror`, one commit (`e66040a1`), 2 files, +100/-9

---

## Title

`fix(context): prefer keys that match the model name over the org prefix`

---

## Summary

### Problem

`_lookup_known()` matches a model id against `KNOWN_CONTEXT_WINDOWS` by
substring and returns the longest matching key. The docstring explains why
longest wins, and it is right about the case it names: `o1` must not shadow
`o1-mini`.

But "longest" is the wrong tiebreak when a key matches inside the **organisation
prefix** of a namespaced id rather than the model name itself.

For `moonshotai/kimi-k2.6`:

- `moonshot` (8 chars) matches, because it is a substring of `moonshotai`
- `kimi-k2` (7 chars) matches the actual model name
- longest wins, so `moonshot` -> **128,000**

The model is served with a 256K window. The agent budgets half of it.

Measured against the table on this branch:

| model id | longest-key picks | this PR picks |
|---|---|---|
| `moonshotai/kimi-k2.6` | `moonshot` -> 128000 | **262144** |
| `moonshotai/kimi-k2-instruct` | `moonshot` -> 128000 | **262144** |
| `kimi-k2` (no org) | `kimi-k2` -> 262144 | 262144 (unchanged) |
| `nvidia/llama-3.1-nemotron-70b` | `llama-3.1` -> 131072 | 131072 (unchanged) |

### Why the under-budget direction is the harmful one

Over-budgeting produces a 400 from the endpoint: loud, immediate, easy to
diagnose. Under-budgeting silently truncates context. The agent keeps working,
drops the earliest turns, and the user sees an assistant that forgot the start of
the conversation with nothing in the logs to say why.

### Fix

Score basename matches at `len(key) * 2` and full-name-only matches at
`len(key)`:

```python
in_basename = key in basename
if not in_basename and key not in name:
    continue
score = len(key) * 2 if in_basename else len(key)
```

Three consequences, all intended:

1. A key matching the actual model name always beats one matching only the org.
2. Among keys matching in the same position, the longest still wins, so the
   `o1` / `o1-mini` guarantee the original docstring was written for is preserved
   unchanged.
3. A key found only in the org portion is still used when the basename matches
   nothing, so `moonshotai/some-unlisted-model` keeps falling back to
   `moonshot`'s 128K rather than dropping to the generic default.

---

## Also in this PR: the table entries that motivate it

The scoring change is unmotivated without the `kimi-k2` entry that exposes it, so
the table additions ship together (34 new keys). Splitting them would leave a
reviewer asking what the scoring fix is for.

Three of them are **corrections to existing values**, and these are worth
calling out separately because they change behaviour for models already in the
table:

| key | was | now | why |
|---|---|---|---|
| `deepseek-v3` | 64000 | 128000 | 64K was the V2-era figure |
| `deepseek-r1` | 64000 | 128000 | same |
| `deepseek-coder` | 64000 | 4096 | NIM serves deepseek-coder-6.7b at 4K; the 64K value made the agent over-send and take 400s |

The rest are models present in the NIM catalog with no key at all, plus more
specific keys that beat an existing shorter one (`mistral-nemo-minitron-8b-8k`
against `mistral-nemo`, `granite-3.0` against `granite-3`, `palmyra-creative`
against `palmyra`). Context windows are from docs.api.nvidia.com, with
llmreference.com as secondary where the primary page 404s. Each non-obvious
value carries its source in a comment.

---

## Verification

Three tests added. The org-prefix guard is **mutation-checked against the
scoring rule alone**, with the table left intact, so the failure isolates the
change under review rather than the new table entries:

```
_lookup_known reverted to longest-key, table unchanged:
  1 failed, 38 passed
    FAILED TestLookupKnown::test_org_prefix_does_not_beat_model_name

branch as submitted:
  39 passed
```

Wider selection, `-k "model_context or context_budget or agent_context"`:
**53 passed**.

The three tests pin: the org-prefix case, that already-correct ids do not move,
and that a key found only in the org portion is still used when the basename
matches nothing.

Two existing tests change expected values (`deepseek-r1` 64000 -> 128000, in the
plain and the namespaced case). Those are the corrected table values above, not
a change in lookup behaviour.

---

## Scope

`src/model_context.py` (+83/-7) and `tests/test_model_context.py` (+26/-2).
