# PR Draft: fix/gguf-quality-scored → pewdiepie-archdaemon/odysseus:dev

**Fork issues:** [#24](https://github.com/jdmanring/odysseus/issues/24) + [#29](https://github.com/jdmanring/odysseus/issues/29)
**Branch:** `fix/gguf-quality-scored` (from `upstream-mirror`)
**Target:** `pewdiepie-archdaemon/odysseus:dev`

---

## Proposed title

`feat(cookbook): quality-scored GGUF source discovery + file selection fixes`

---

## PR description (for upstream reviewers)

### Problem

When downloading a llamacpp model that has no static `ggufSource` configured,
the app has no way to find the community-quantized GGUF repo automatically.
Users must know to search HuggingFace for a third-party quantization (e.g.,
`bartowski/Meta-Llama-3.1-8B-GGUF`) and enter it manually.

Additionally, the existing file-selection logic had two bugs affecting models
that do reach the downloader:

1. **mmproj companion file selected for vision models.** Repos like
   `Leafspark/Llama-3.2-11B-Vision-Instruct-GGUF` publish both the quantized
   model weights and a `*-mmproj.f16.gguf` projector companion file. The
   resolver was returning `files[0]` from the raw HF sibling list — which,
   depending on upload order, could be the tiny mmproj file rather than the
   actual model weights.

2. **`source.file` overrode `model.quant`.** When the resolver returned any
   file, `_ggufIncludePattern` used it directly as the include pattern —
   silently ignoring the model's own `quant` field (e.g. `Q4_K_M`). A model
   whose name and UI clearly indicated Q4_K_M could end up downloading Q2_K
   or the mmproj file instead.

### Solution

**Auto-discovery with quality scoring**

`HfUrlResolver.find_gguf_sources(base_repo_id)` searches HuggingFace for
`"{model_name} GGUF"`, then probes each candidate via the HF metadata API
(a single `model_info(expand=[...])` call per repo — no file download needed).
Results are scored on eight signals and sorted by score descending.

| Signal | Max pts | Rationale |
|--------|---------|-----------|
| Downloads (log-scale) | 40 | Strongest community trust signal |
| Likes ratio | 10 | High ratio = strong approval relative to reach |
| Has benchmark evals | 10 | Well-tested = well-maintained |
| Best eval score | 10 | Higher benchmark = higher quality |
| HF trending score | 5 | Recent momentum |
| Imatrix calibration | 15 | Measurably better quality at same bit width |
| Author reputation | 10 | Known high-quality quantizers (bartowski, TheBloke, etc.) |
| Recency | 5 | Recently updated = actively maintained |

The top-scored result is injected silently as `ggufSource` — no UI change.

**mmproj filter**

`_probe_gguf_repo` now excludes any GGUF file whose name contains `mmproj`
from the candidate file list. This ensures vision model repos only surface
actual model weights through the resolver.

**`model.quant` takes precedence**

`_ggufIncludePattern` now checks `model.quant` before `source.file`. If the
model has a quant configured (e.g. `Q4_K_M`), that drives the include pattern
(`*Q4_K_M*`) regardless of what the resolver found. `source.file` is still
used as a fallback for cases where the resolver has a specific file hint and
the model has no quant set; `*.gguf` is the final fallback.

### Reputed author list

The `_REPUTED_AUTHORS` set contains quantizers with a demonstrated track
record of quality and maintenance:

- **S-tier**: `bartowski` (imatrix, recommended collections), `TheBloke` (largest catalog)
- **A-tier**: `mradermacher` (imatrix I1/I2), `MaziyarPanahi`, `tensorblock`
- **B-tier**: `legraphista`, `duyntnet`, `second-state`

All three imatrix quantizers (`bartowski`, `duyntnet`, `mradermacher`) also
receive the imatrix bonus, so they rank higher than equally-downloaded
non-imatrix repos.

### Files changed

| File | Change |
|------|--------|
| `tooling/hf_url_resolver.py` | Complete rewrite of `_probe_gguf_repo` with expand= quality signals; new `_score_candidate`, `_REPUTED_AUTHORS`, `_IMATRIX_AUTHORS`, `_detect_imatrix`; updated `find_gguf_sources` to sort by quality score; mmproj filter |
| `routes/cookbook_routes.py` | `GET /api/cookbook/resolve-gguf` endpoint (unchanged from prior simple version) |
| `static/js/cookbookDownload.js` | Auto-discovery call in `_runModelDownload`; `_ggufIncludePattern` reordered to check `model.quant` first; resolver source mapped with `file: null` so model.quant drives selection |

### Backward compatibility

- Models with a static `ggufSource` configured are unaffected — discovery
  only fires when `backend === 'llamacpp' && !ggufSource`.
- The `resolve-gguf` endpoint is additive; no existing routes changed.
- `_ggufIncludePattern` fallback chain (`model.quant` → `source.file` →
  `*.gguf`) preserves all previous behavior for models that don't use
  auto-discovery.

### Testing

- Llama-3.2-11B-Vision-Instruct (llamacpp, no static ggufSource): resolver
  finds the correct repo; download uses `*Q4_K_M*` include pattern, not the
  mmproj file.
- DeepSeek-V2-Lite-Chat (llamacpp, no static ggufSource): resolver selects a
  reputed quantizer; Q4_K_M variant downloaded, not Q2_K.
- Model with `quant: "Q5_K_M"` configured: `*Q5_K_M*` include pattern used
  regardless of what the resolver returned.
- `GET /api/cookbook/resolve-gguf?model=meta-llama/Llama-3.1-8B`: returns
  ranked results with `quality_score` field; bartowski or mradermacher repos
  appear at the top.
- Model with no community GGUF repos: graceful fallback to existing
  "No GGUF source configured" error toast.
- Discovery works without a HF token (public repos don't require auth).

---

## Filing notes

1. No upstream issue needed first — open the PR directly. Reference issues
   #24 and #29 in the fork tracker as context.
2. Target branch: `dev` (not `main`).
3. This PR can be filed independently of `feat/aria2c-downloader` — the
   auto-discovery path works with the standard `hf download` fallback too.
4. The `_REPUTED_AUTHORS` list is a starting point; upstream maintainers may
   want to add or remove names based on their own assessment.
