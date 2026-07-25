# Upstream Issue Draft: feat-gguf-discovery

**File on:** `odysseus-dev/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/feat-gguf-discovery.md`
**Branch:** `fix/gguf-quality-scored`
**Type:** Enhancement / Bug fix
**References:** Addresses the symptom described in #2342

---

## Title

`[Cookbook] Quality-scored GGUF source discovery, find the best community quantization automatically`

---

## Body

**Area:** Cookbook / GGUF downloads / llamacpp backend

**Problem / Motivation:**
When a llamacpp model has no static `ggufSource` configured, the auto-discovery feature searches HuggingFace for `"{model_name} GGUF"` and sorts by download count. This has two problems:

1. **Discovery returns low-quality results.** Sorting by downloads alone surfaces repositories with "GGUF" in the name but no actual GGUF files, old unmaintained repos, and repos from quantizers with a poor track record. Users see "No GGUF source is configured" for popular models even when high-quality community quantizations exist (addresses #2342).

2. **File selection ignores the model's configured quantization.** When the resolver returns a repository, `_ggufIncludePattern` uses `source.file` as the include pattern: silently ignoring the model's own `quant` field (e.g. `Q4_K_M`). A model whose name and UI clearly indicate Q4_K_M can end up downloading Q2_K or a projector companion file (`*-mmproj.f16.gguf`) instead.

**Proposed Solution:**
Replace the download-count sort with an 8-signal quality scorer:

| Signal | Max pts | Rationale |
|--------|---------|-----------|
| Downloads (log-scale) | 40 | Strongest community trust signal |
| Likes ratio | 10 | Strong approval relative to reach |
| Has benchmark evals | 10 | Well-tested = well-maintained |
| Best eval score | 10 | Higher benchmark = higher quality |
| HF trending score | 5 | Recent momentum |
| Imatrix calibration | 15 | Measurably better quality at same bit width |
| Author reputation | 10 | Known high-quality quantizers |
| Recency | 5 | Recently updated = actively maintained |

Additionally:
- **mmproj filter:** exclude `*-mmproj*.gguf` companion files from candidate selection
- **`model.quant` precedence:** check `model.quant` before `source.file` when building the include pattern
- **Tier-aware closest-quant fallback:** when the exact quant isn't available, select the best available quant in the same bit-depth tier rather than the first alphabetical file

**Alternatives Considered:**
Direct HuggingFace leaderboard API: requires OAuth and returns model performance, not quantization quality. The 8-signal scorer uses only public metadata from `model_info(expand=[...])`; one API call per candidate, no authentication required.
