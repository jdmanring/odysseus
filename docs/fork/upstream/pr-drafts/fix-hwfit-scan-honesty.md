# PR Draft: fix/hwfit-scan-honesty -> odysseus-dev/odysseus:dev

**Branch:** `fix/hwfit-scan-honesty`
**Status:** Ready to file
**Base:** cut from `upstream-mirror`, 6 files, +300/-46

---

## Title

`feat(hwfit): architecture servability gate; sort and filter honesty in the scan UI`

---

## Summary

Three defects in the hardware-fit scan, all of which mislead the user in the same
direction: the UI claims something the system cannot deliver.

### 1. "Fit" rated models that cannot run at all

Fit has only ever meant *fits your VRAM*. So the scan rated a research checkpoint
— `Qwen3DSparkModel`, for which **no inference code exists anywhere** — as
`PERFECT`, and let the user download it and launch it into a guaranteed engine
rejection.

VRAM sufficiency is necessary and not sufficient. Adds an architecture
servability gate so a model no engine can load is never rated runnable.

### 2. The quant filter did not apply to Ollama rows

The filter was applied **server-side only**, and client-synthesized Ollama rows
(all `Q4_K_M`) were concatenated *after* filtering. So "only Q6" still returned
`Q4_K_M` rows — a filter that silently does not filter part of its own result set.
Ollama rows now pass the same exact-tier filter.

### 3. Column sort ran the entire fetch pipeline

A sort click ran localStorage parse, a ~2500-row render, a server refetch, and a
second full render — for a **pure in-memory table operation**. Reported as
"tremendous lag" on the Score column.

The sort block is extracted to `_sortHwfitModels()`, and the click handler calls
`_hwfitResort()` (sort and repaint from the already-loaded scan), falling back to
a fetch only when no scan is loaded.

---

## Why these ship together

They are one surface and one theme: the scan should not report more confidence
than it has. Sorting is the odd one out mechanically, but it is the same file and
the same user session, and splitting it would mean two PRs touching
`cookbook-hwfit.js` in sequence.

---

## Verification

**10 passed**, measured 2026-08-03, across the servability/identity tests
(`test_hwfit_no_fabricated_gguf_identity.py`) and the UI wiring tests
(`test_hwfit_ui_wiring.py`, which pins that the sort path does not refetch).

---

## Scope

`services/hwfit/hf_discovery.py` (+37), `static/js/cookbook-hwfit.js` (+114/-…),
`static/js/cookbook.js`, two test files.
