# PR Draft: feat/gguf-discovery → pewdiepie-archdaemon/odysseus:dev

**Branch:** `jdmanring/odysseus:feat/gguf-discovery`
**Base:** `jdmanring/odysseus:feat/aria2c-downloader` (file after #12 merges)
**Issue:** [#24](https://github.com/jdmanring/odysseus/issues/24) (fork tracking)
**Status:** Ready to file after feat/aria2c-downloader (#12) merges upstream

---

## Title

`feat(cookbook): dynamic GGUF source discovery for llamacpp backend`

---

## Description

### Problem

When adding a llamacpp model to Cookbook, users must manually supply a
`ggufSource` (the HuggingFace repo ID that hosts GGUF quantizations). Most
base models (e.g., `meta-llama/Llama-3.1-8B`) do not host GGUF files
directly — community-quantized versions exist on separate repos (e.g.,
`bartowski/Meta-Llama-3.1-8B-GGUF`). There is no way for the app to
discover these automatically; users have to know to look for them and
manually enter the source repo ID.

### Solution

Add an auto-discovery path that searches HuggingFace for community GGUF
quantizations when no static `ggufSource` is configured.

**`HfUrlResolver.find_gguf_sources(base_repo_id)`**

Extracts the model name from the repo ID, then calls:
```python
api.list_models(search=f"{model_name} GGUF", sort="downloads", direction=-1, limit=10)
```
Returns a list of repo IDs sorted by download count, excluding the base repo.

**`GET /api/cookbook/resolve-gguf?model=<repo_id>`**

New endpoint that calls `find_gguf_sources` and returns:
```json
{ "gguf_sources": ["bartowski/Model-GGUF", "TheBloke/Model-GGUF", ...] }
```

**Auto-discovery in `cookbookDownload.js`**

In `_runModelDownload`, when `backend === 'llamacpp'` and no `ggufSource`
is present, calls `/api/cookbook/resolve-gguf` before the download starts.
If sources are found, injects the top result as `ggufSource` and the download
proceeds without user intervention. Falls through to existing error handling
if discovery fails or returns no results.

### Files Changed

- `tooling/hf_url_resolver.py` — `find_gguf_sources()` method
- `routes/cookbook_routes.py` — `/api/cookbook/resolve-gguf` GET endpoint
- `static/js/cookbookDownload.js` — auto-discovery call in `_runModelDownload`

### Notes

- Discovery works with or without a HF token (public GGUF repos don't require auth)
- The injected `ggufSource` is not persisted — it is resolved fresh each download
- No UI change: discovery is silent; the download card appears normally

### Testing

- [x] Add a llamacpp model with no ggufSource — verify download finds and uses
  a community GGUF repo automatically
- [x] Verify the endpoint returns a ranked list: `GET /api/cookbook/resolve-gguf?model=meta-llama/Llama-3.1-8B`
- [x] Verify graceful fallback when model has no community quantizations

---

## Filing Notes

This branch is built on top of `feat/aria2c-downloader`. File this PR after
that one merges. The PR should target `dev`.
