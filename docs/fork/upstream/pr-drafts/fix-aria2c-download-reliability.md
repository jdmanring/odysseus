# PR Draft: fix/aria2c-download-reliability → pewdiepie-archdaemon/odysseus:dev

**Branch:** `jdmanring/odysseus:fix/aria2c-download-reliability`
**Base:** `jdmanring/odysseus:feat/aria2c-downloader` (file after #12 merges)
**Issue:** [#23](https://github.com/jdmanring/odysseus/issues/23) (fork tracking)
**Status:** Ready to file after feat/aria2c-downloader (#12) merges upstream

---

## Title

`fix(downloader): aria2c reliability fixes and download card UI bugs`

---

## Description

### Problem

Several bugs and reliability issues in the aria2c download pipeline discovered
through testing:

**1. Download card shows wrong filename (per-file rows)**

tmux sessions are created without an explicit terminal width, defaulting to
80 columns. aria2c's `FILE:` progress lines — e.g.:
```
FILE: /home/user/.cache/huggingface/hub/models--owner--ModelName/snapshots/{commit}/file.safetensors
```
exceed 80 chars. tmux wraps at column 80; the JS progress parser's `(\S+)`
regex captures only the first visual line, ending at the HF cache directory
name rather than the actual filename. Per-file rows show the model directory
instead of the real shard name (e.g., `model-00001-of-00005.safetensors`).

**2. "X of N files" stat disappears mid-download**

`aria2c_download.py` prints `[*] N file(s) to download` once at startup.
With `--summary-interval=3` and 4 parallel files, the banner scrolls out of
the 200-line `tmux capture-pane` window after ~3–4 minutes. `totalFiles`
resolves to 0 and the file-count stat vanishes from the download card.
`_dlFileTracker.totalFileCount` caches the value but `fileCtx` reads from
the outer `totalFiles` variable instead — the cached value was never used.

**3. HF endpoint throttling with 16 connections per file**

`conn_per_file = 16` was causing connection throttling/rejections from the
HuggingFace CDN for some models, leading to failed or stalled downloads.

**4. aria2c input file uses space-indented options (non-canonical)**

aria2c's input file format specifies tab-indented per-URL options. The code
used 2 spaces, which aria2c tolerates but is not canonical.

**5. `--download-result=hide` suppresses completion info**

Silencing the result summary made it harder to diagnose partial failures.

**6. No verification that files were actually downloaded**

aria2c can exit 0 on partial failure in some edge cases. No post-download
check confirmed files were actually written.

**7. `hf_url_resolver.py` fails silently when `list_repo_files` errors**

No fallback when the HuggingFace Hub library raises an exception during
file enumeration. The `include` filter also didn't match against
`os.path.basename(f)`, so glob patterns like `*.gguf` silently skipped
files in subdirectories.

### Fix

- Pass `-x 220 -y 50` to every `tmux new-session` call so FILE: paths fit
  on one visual line for any realistic HF cache path
- Change `const totalFiles` → `let` in `_parseDownloadState`; add fallback
  to `tr.totalFileCount` inside the tracker block when `totalFiles` is 0
- Reduce `conn_per_file` from 16 to 3 (4×3 = 12 total connections)
- Use tab indentation in aria2c input file
- Change `--download-result=hide` to `--download-result=full`
- Add post-download check: `sys.exit(1)` if output directory is empty
- Add HTTP API fallback in `resolve_snapshot_urls` when `list_repo_files`
  fails; fix `include` filter to also check `os.path.basename(f)`

### Files Changed

- `tooling/aria2c_download.py`
- `tooling/hf_url_resolver.py`
- `routes/cookbook_routes.py` (tmux width only)
- `static/js/cookbookRunning.js`

### Testing

- [x] Download a multi-file model (e.g., 3B+ model with multiple shards) —
  verify per-file rows show real filenames, not model directory names
- [x] Let a multi-shard download run past 3 minutes — verify file count stat
  stays visible throughout
- [x] Verify aria2c exits correctly on network error (no silent partial download)

---

## Filing Notes

This branch is built on top of `feat/aria2c-downloader`. File this PR after
that one merges. The PR should target `dev`.
