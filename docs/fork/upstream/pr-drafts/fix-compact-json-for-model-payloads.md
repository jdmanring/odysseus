# PR Draft: fix/compact-json-for-model-payloads -> odysseus-dev/odysseus:dev

**Branch:** `fix/compact-json-for-model-payloads`
**Issue:** #190 (fork tracking)
**Status:** Ready to file. Independent of every other staged branch.
**Base:** cut from `upstream-mirror` (`fb8c391a`), one commit

*Line numbers against `upstream-mirror`.*

---

## Title

`fix(context): stop spending the model's payload budget on indentation`

---

## Summary

Three formatters serialize a structure with `json.dumps(..., indent=2)`, feed
the result to the model, and then truncate it at a character cap. The
indentation is spent against that cap, so whitespace displaces the data it is
indenting.

| site | cap | carries |
|---|---|---|
| `src/tool_execution.py:1033` | 8000 | the `extra` payload of every tool result: events, tasks, notes, documents, attachments |
| `src/integrations.py:475` | 12000 | HTTP integration response bodies |
| `src/tools/system.py:714` | 4000 | API-call preview |

## This is data loss, not a cost tweak

Measured with `tiktoken` (`cl100k_base`) on payload shapes these formatters
actually surface:

| payload | `indent=2` | compact | saving |
|---|---:|---:|---:|
| calendar events (40) | 3584 tok | 2499 tok | 30.3% |
| memories (40) | 2578 tok | 1613 tok | 37.4% |
| tasks (40) | 2449 tok | 1443 tok | 41.1% |
| nested report (non-uniform) | 119 tok | 58 tok | 51.3% |

Against `format_tool_result`'s 8000-char cap:

```
calendar events (40)   9905 chars pretty  TRUNCATED   |  6937 compact  fits
memories (40)          8182 chars pretty  TRUNCATED   |  5534 compact  fits
```

A 40-event calendar query is cut off mid-object today, and the model answers
from a partial structure. Two of the four shapes cross the cap on indentation
alone.

## `src/integrations.py` is worth reading twice

That block already binary-searches for the largest array prefix that fits the
cap, so it truncates at item boundaries rather than mid-object. That is careful
work, and pretty-printed input starves it. On a 400-event response it now emits
**69 items in 11845 chars** where it previously managed 53.

All five `json.dumps` calls in the block move together, deliberately: the
search has to measure the encoding it emits. Leaving one on `indent=2` would
compute the fit against a string that is never sent — and the tests cover both
halves of that mistake, because parsing alone does not catch it (a
pretty-printed body still parses and still reports the right item count).

## Scope

- **Lossless.** `json.loads(compact) == original` on every shape tested. Same
  JSON, same data; models parse minified JSON without difficulty.
- **`ensure_ascii=False` preserved.** Escaping non-ASCII would give back more
  than the separators save.
- **Caps unchanged.** This is an encoding fix, not a cap removal, and a test
  pins that.
- **Config writes left alone.** The two remaining `indent=2` calls in
  `integrations.py` write files to disk for humans to read.

## Deliberately not proposed

A token-oriented format such as TOON, which reached 52-62% on the uniform
arrays above in local measurement. It is a new dependency and a format change,
and it is **not** uniformly better: on the `tasks` payload, whose rows carry a
`tags` list, it fell out of its tabular form and scored 24.8% against compact
JSON's 41.1%. That belongs in its own PR with its own measurement against the
published library. The figures here for it came from a local approximation and
are indicative only; every compact-JSON figure in this PR is exact.

## Tests

`tests/test_model_payload_encoding.py`, 8 tests. They assert on the **emitted
string**, not on source text, so a formatter reverting to `indent=` fails
however that is spelled. The integration tests drive the real
`execute_api_call` with a stubbed transport rather than restating its
formatting.

Six mutations verified to fail the suite: each site reverted to `indent=2`,
both halves of a measure/emit mismatch, `ensure_ascii` flipped, and the cap
removed. The under-fill bound was first set by guess at 9000 chars and the
mutant slipped through by 109; it is now derived from both measurements
(correct 11845, mutant 9109).

Full suite: 4797 passed, 1 skipped.
