# PR Draft: fix/gguf-quality-scored → pewdiepie-archdaemon/odysseus:dev

**Fork issues:** [#24](https://github.com/jdmanring/odysseus/issues/24) + [#29](https://github.com/jdmanring/odysseus/issues/29)
**Branch:** `fix/gguf-quality-scored` (from `upstream-mirror`)
**Target:** `pewdiepie-archdaemon/odysseus:dev`

---

## Proposed title

`feat(cookbook): quality-scored GGUF source discovery + file selection fixes`

---

## PR description (for upstream reviewers)

*Closes #2342.*

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

**Tier-aware closest-quant fallback**

When `model.quant` is set but the discovered repo doesn't have that exact
variant (e.g. a Q4_K_M request against an imatrix-only repo like
`legraphista/DeepSeek-V2-Lite-Chat-IMat-GGUF`), `_closestQuantFile` finds the
best available alternative. The algorithm uses a flat quality ranking
(`_QUANT_QUALITY`, best to worst) and a tier-range table (`_QUANT_TIER_RANGES`)
that groups quants by bit-depth family (all Q4*/IQ4* quants are tier 4, etc.).

Selection priority:
1. **Same-tier best**: if the repo has any quant in the same bit-depth tier as
   the requested quant, the best one in that tier wins (lowest quality index).
   This means IQ4_XS wins over Q4_K_S when Q4_K_M was requested — imatrix
   calibration is an objective upgrade within the same tier.
2. **Cross-tier nearest**: if nothing is in the same tier, pick the quant in
   the closest adjacent tier. For equidistant tiers (one above, one below),
   prefer the smaller file (go down a tier) to avoid overshooting the user's
   intended file size.

Within each tier, imatrix variants lead the ranking (IQ4_XS → IQ4_NL → Q4_K_M
→ Q4_K_S → Q4_1 → Q4_0) so the same-tier rule automatically selects the best
available quantization method, not just the closest name.

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
| `static/js/cookbookDownload.js` | Auto-discovery call in `_runModelDownload`; `_ggufIncludePattern` reordered to check `model.quant` first; resolver source mapped with `file: null` so model.quant drives selection; `_QUANT_QUALITY` flat ranking list; `_QUANT_TIER_RANGES` + `_quantTierRank`; tier-aware `_closestQuantFile` |

### Relation to ROADMAP

This directly addresses the ROADMAP item:

> *Cookbook model scan/download ranking. Prioritize newer architectures and
> better hardware-fit models instead of scoring everything almost the same.
> Ranking should account for architecture age, quant format, VRAM/RAM fit,
> backend support, **vision/mmproj requirements**, and likely serve reliability.*

The 8-signal scorer differentiates repos where the old sort-by-downloads approach
scored them nearly the same. The mmproj filter and `model.quant` precedence fix
the vision/mmproj case the ROADMAP calls out explicitly. Architecture age,
VRAM/RAM fit, and backend support remain future work.

### Backward compatibility

- Models with a static `ggufSource` configured are unaffected — discovery
  only fires when `backend === 'llamacpp' && !ggufSource`.
- The `resolve-gguf` endpoint is additive; no existing routes changed.
- `_ggufIncludePattern` fallback chain (`model.quant` → `source.file` →
  `*.gguf`) preserves all previous behavior for models that don't use
  auto-discovery.

### Checks run

```bash
# Syntax check — all modified Python files
python -m py_compile tooling/hf_url_resolver.py routes/cookbook_routes.py
# JS check
node --check static/js/cookbookDownload.js
# Existing test suite (no new tests cover this code path — see note below)
python -m pytest
```

The `_probe_gguf_repo`, `_score_candidate`, and `_ggufIncludePattern` code paths
are not covered by existing automated tests. Manual in-app testing was the primary
verification method (see Testing below). If upstream adds test infrastructure for
the cookbook routes, coverage for this path would be a good addition.

### Testing

- Llama-3.2-11B-Vision-Instruct (llamacpp, no static ggufSource): resolver
  finds the correct repo; download uses `*Q4_K_M*` include pattern, not the
  mmproj file.
- DeepSeek-V2-Lite-Chat via `legraphista/DeepSeek-V2-Lite-Chat-IMat-GGUF`
  (imatrix-only repo, no Q4_K_M file): closest-quant fallback selects IQ4_XS
  (best in tier 4), not Q2_K or the first alphabetical file.
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

1. **Closes upstream #2342** — "Auto-discovered models without `gguf_sources`
   appear as llama.cpp-ready but fail to download with no clear guidance."
   Reference this in the PR body. The bug reporter is on Windows 11 with an
   RTX 4080 Super — this fix is not platform-specific.
2. Target branch: `dev` (not `main`).
3. This PR can be filed independently of `feat/aria2c-downloader` — the
   auto-discovery path works with the standard `hf download` fallback too.
4. The `_REPUTED_AUTHORS` list is a starting point; upstream maintainers may
   want to add or remove names based on their own assessment.
5. Fork tracker context: issues #24 and #29 on `jdmanring/odysseus`.
