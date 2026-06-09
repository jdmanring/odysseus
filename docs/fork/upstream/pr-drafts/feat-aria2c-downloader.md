# PR Draft: feat/aria2c-downloader → pewdiepie-archdaemon/odysseus:dev

**Branch:** `jdmanring/odysseus:feat/aria2c-downloader`
**Issue:** [#12](https://github.com/jdmanring/odysseus/issues/12) + [#23](https://github.com/jdmanring/odysseus/issues/23) (fork tracking)
**Status:** Needs integration test run + screenshot before filing

---

## Title

`feat(cookbook): aria2c parallel download system with real-time progress UI`

---

## Description

### Problem

The existing `hf download` CLI downloader is single-threaded and provides no
real-time progress feedback in the UI — users see a spinner until the download
completes or fails. Large models (7B+) can take many minutes with no indication
of speed, ETA, or per-file status.

### Solution

A tmux-backed aria2c download pipeline with a real-time per-file progress
card in the Cookbook UI.

### Backend

**`tooling/bin_manager.py`** — portable binary installer. Auto-downloads the
correct aria2c release for the current platform (linux/mac/windows x86/arm)
and caches it in `~/.odysseus/bin`. No system package manager required.

**`tooling/aria2c_download.py`** — one-shot download script that:
- Resolves HF repo files to pinned signed URLs via `HfUrlResolver`
- Writes an aria2c input file (tab-indented options, Bearer auth header)
- Spawns aria2c with 4 parallel files × 3 connections each (12 total —
  tuned to avoid HF CDN throttling)
- Verifies the output directory is non-empty after aria2c exits 0

**`tooling/hf_url_resolver.py`** — resolves a HF repo to a list of
`(signed_url, relative_path)` tuples pinned to the HEAD commit hash.
Includes an HTTP API fallback when the huggingface_hub library fails, and
a basename-aware `include` filter so `*.gguf` correctly matches files in
subdirectories.

**`routes/cookbook_routes.py`** — `use_aria2c` path in `model_download`:
- Copies `tooling/` to remote host when needed
- Sets `tmux new-session -x 220 -y 50` to prevent 80-col truncation of
  `FILE:` progress lines (would cause wrong filename display in the UI)
- Passes HF token as both `HF_TOKEN` env var and `--token` arg to
  `aria2c_download.py`

**`routes/cookbook_helpers.py`** — adds `use_aria2c: bool = False` to
`ModelDownloadRequest`; sets `disable_hf_transfer` default to `True`.

### Frontend

**`static/js/cookbookDownload.js`** — `_startManagedPolling()` drives the
download card; `_runModelDownload()` routes to the aria2c path when `use_aria2c`
is set.

**`static/js/cookbookRunning.js`** — `_parseDownloadState()` parses aria2c
stdout (parallel progress lines, `FILE:` path, `[*] N files` banner).
`_dlFileTracker` accumulates per-file byte counts across poll ticks.
`totalFiles` falls back to `_dlFileTracker.totalFileCount` when the startup
banner scrolls out of the 200-line `capture-pane` window.

**`static/style.css`** — download card, per-file progress rows, cancel button.

### Tests

**`tests/test_aria2c_circuit.py`** — BinManager unit tests: platform detection,
URL construction, cache path logic, download verification.

### Files Changed

- `tooling/aria2c_download.py` (new)
- `tooling/bin_manager.py` (new)
- `tooling/hf_url_resolver.py` (new)
- `tests/test_aria2c_circuit.py` (new)
- `routes/cookbook_routes.py`
- `routes/cookbook_helpers.py`
- `static/js/cookbookDownload.js`
- `static/js/cookbookRunning.js`
- `static/style.css`

### Testing

- [ ] Download a single-file model — verify progress card appears, completes,
  and the file appears in the model list
- [ ] Download a multi-shard model (5+ files) — verify per-file rows show
  correct filenames and the overall percentage stays accurate past the 3-minute
  mark
- [ ] Download a gated model with a valid HF token — verify auth works
- [ ] Cancel mid-download — verify tmux session is killed and no partial files
  are left in an inconsistent state
- [ ] After a successful download, verify the cached dot (●) appears on the
  model row immediately without a page reload
- [ ] Download a GGUF model — verify the cached dot appears using the GGUF
  repo name, not the catalog entry name
- [ ] Run `pytest tests/test_aria2c_circuit.py` — should pass

---

## Filing Notes

This PR can be filed independently. `feat/gguf-discovery` (#24) is a follow-up
that adds auto-discovery of GGUF sources for llamacpp models — file after this
one merges.
