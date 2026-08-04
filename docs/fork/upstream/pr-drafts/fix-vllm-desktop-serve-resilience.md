# PR Draft: fix/vllm-desktop-serve-resilience -> odysseus-dev/odysseus:dev

**Branch:** `fix/vllm-desktop-serve-resilience`
**Status:** Ready to file
**Base:** cut from `upstream-mirror`, 4 files, +169

---

## Title

`fix(serve): vLLM launches survive a missing CUDA toolkit and a KV-cache ceiling`

---

## Summary

Two gates in the same launch sequence, both of which stop a model that would
otherwise run.

### 1. flashinfer aborts the engine when `nvcc` is absent

flashinfer JIT-compiles its sampling kernel at startup and **aborts the whole
engine** if there is no compiler. It assumes `/usr/local/cuda`; Arch-family
systems put CUDA at `/opt/cuda`, and most inference boxes have no toolkit
installed at all.

Sampling does not need a compiler. Failing the entire launch because an optional
JIT path cannot build is a hard failure for an optional optimisation.

The serve runner now points `CUDA_HOME` at `/opt/cuda` when `nvcc` is there, and
otherwise exports `VLLM_USE_FLASHINFER_SAMPLER=0` to take vLLM's native sampler.
Both paths run the model; only the sampler implementation differs.

### 2. The KV-cache context ceiling was reported as an opaque failure

Final gate in the Qwen3-8B.w8a8 sequence: model and workspace fit, but
`max_model_len 40960` needs **5.62 GiB** of KV cache against **3.06 GiB**
remaining. vLLM states the roughly 22k ceiling in its own error text, and the UI
discarded it.

All three diagnosis surfaces now match that error and offer **one-click retries
at context 16384 / 8192**. The information was already in the failure; the fix is
not throwing it away.

---

## Why this is worth upstreaming

Both failures present to the user as "the model did not start", with the actual
cause buried in engine stderr. Neither is a bug in vLLM: one is an environment
assumption, the other is a real resource limit that was simply not surfaced.

---

## Verification

**4 passed**, measured 2026-08-03, in `tests/test_vllm_serve_resilience.py`
(toolkit-present, toolkit-absent, and the context-ceiling parse).

---

## Scope

`routes/cookbook_routes.py` (+44), `static/js/cookbook-diagnosis.js` (+32), the
serve runner, one test file.
