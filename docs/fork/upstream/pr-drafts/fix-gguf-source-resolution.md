# PR Draft: fix/gguf-source-resolution → pewdiepie-archdaemon/odysseus:dev

**Branch:** `jdmanring/odysseus:fix/gguf-source-resolution`
**Issue:** [#29](https://github.com/jdmanring/odysseus/issues/29) (fork tracking)
**Status:** Ready to file

---

## Title

`feat(cookbook): quality-scored GGUF source discovery for llamacpp`

---

## Summary
### Problem

When downloading a model with the llamacpp backend and no `ggufSource` configured, the auto-discovery feature (`/api/cookbook/resolve-gguf`) searches HuggingFace for `"{model_name} GGUF"` and returns the top results by downloads. This often surfaces low-quality or irrelevant repos — repos with "GGUF" in the name but no actual GGUF files, or quantizers that don't match recognized formats.

Users see "No GGUF source is configured" for popular models because the discovery results don't contain usable quantization repos.

### Solution

Score candidate repos by quality signals and filter to only return repos with at least one strong signal:

- **+100** — repo name contains a recognized quantization format (`Q4_K_M`, `IQ4_XS`, `F16`, etc.)
- **+50** — repo name contains "GGUF" explicitly
- **+25** — repo name contains the exact model name
- **+10** — repo owner matches the base model's owner (official quantizations)

Results are sorted by score first, then by downloads within each tier. Only repos with a minimum score (at least "GGUF" in name) are returned.

### Files Changed

- `tooling/hf_url_resolver.py` — new file: `HfUrlResolver` with `find_gguf_sources()` and `_score_gguf_repo()`
- `routes/cookbook_routes.py` — `GET /api/cookbook/resolve-gguf` endpoint
- `static/js/cookbookDownload.js` — auto-calls `resolve-gguf` for llamacpp models with no static `ggufSource`

## Checklist

- [x] I searched [open issues](https://github.com/pewdiepie-archdaemon/odysseus/issues) and [open PRs](https://github.com/pewdiepie-archdaemon/odysseus/pulls) — this is not a duplicate.
- [x] This PR targets `dev`
- [x] My changes are limited to the scope described above — no unrelated refactors or whitespace changes mixed in.
- [x] I actually ran the app (`docker compose up` or `uvicorn app:app`) and verified the change works end-to-end. Type-checks and unit tests are not enough.

## How to Test
- [ ] Run `pytest tests/test_aria2c_circuit.py` — existing tests pass
- [ ] In the app: try downloading a llamacpp model with no `ggufSource` — verify the resolve-gguf endpoint returns quality results
- [ ] Verify the discovered sources appear in the download form

---



## Target branch

- [x] This PR targets **`dev`**, not `main`. All PRs land in `dev`; `main` is curated by the maintainer at each release.

## Linked Issue

Fixes # <!-- [file upstream issue first] -->

## Type of Change

- [ ] Bug fix (non-breaking — fixes a confirmed issue)
- [x] New feature (non-breaking — adds new behaviour)
- [ ] Breaking change (changes or removes existing behaviour)
- [ ] Refactor / cleanup (behaviour unchanged)
- [ ] Documentation only
- [ ] CI / tooling / configuration

## Filing Notes

This is a standalone feature with no dependencies. Can be filed in any order.

## Visual / UI changes

None — no HTML, CSS, or DOM-writing JS was changed.
