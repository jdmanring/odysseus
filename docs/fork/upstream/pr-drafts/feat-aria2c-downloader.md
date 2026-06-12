# PR Draft: feat/aria2c-downloader → pewdiepie-archdaemon/odysseus:dev

**Branch:** `jdmanring/odysseus:feat/aria2c-downloader`
**Issue:** [#12](https://github.com/jdmanring/odysseus/issues/12) + [#23](https://github.com/jdmanring/odysseus/issues/23) (fork tracking)
**Status:** Bugs found in integration testing — fixed 2026-06-12, re-verify before filing

---

## Title

`feat(cookbook): aria2c parallel download system with real-time progress UI`

---

## Description

### Problem

Three open upstream issues point to the same underlying gap in the Cookbook
download stack:

- **Issue #359** — *"Show Download Percentage During Cookbook Downloads"*:
  users see a spinner until the download completes or fails. No speed, ETA, or
  per-file progress is visible. For large models this is a black box for ten or
  more minutes.

- **Issue #2722** — *"Cookbook large HF model downloads crash/restart due to
  SSL ReadError"*: HuggingFace CDN connections drop on large files. The current
  `hf download` CLI has no retry logic — a single SSL error aborts the entire
  download and the user must start over from zero.

- **Issue #787** — *"Add pause and resume functionality for model downloads"*:
  no way to interrupt a download and continue later, which is a hardship for
  users on slow or metered connections.

All three share a root cause: the existing `hf download` CLI is single-threaded,
has no built-in retry, exposes no structured progress output, and leaves no
partial files that could be resumed. Fixing any one of them correctly requires
replacing the downloader itself.

### Solution

A tmux-backed aria2c download pipeline with a real-time per-file progress
card in the Cookbook UI. This closes #359, substantially mitigates #2722, and
lays the groundwork for full pause/resume (#787 — see notes).

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
banner scrolls out of the 200-line `capture-pane` window. `isSingleFileSplit`
detects when all `perFileData` entries share a filename (one file downloaded as
N pieces with `--split=N`) and skips the multi-batch tracker for that case —
the raw aria2c `pct` already sums pieces correctly.

**`static/js/cookbook-hwfit.js`** — `refreshCachedModelIds()` now handles local
downloads (no `remoteHost`). Previously returned early for empty host, making
the downloaded-dot re-mark a no-op for local installs. Both Running tab
done-transition paths now call `refreshCachedModelIds` so the catalog dot
appears immediately without a page reload.

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
- `static/js/cookbook-hwfit.js`
- `static/style.css`

### Relation to ROADMAP

This directly addresses two ROADMAP items:

> *Cookbook reliability on other computers. This is probably the area most
> likely to need work across different machines, GPUs, drivers, shells, and
> Python environments.*

aria2c is self-installed per-platform (linux/mac/windows × x86/arm) by
`BinManager` — no system package manager, no `apt`, no `brew`. The binary is
cached in `~/.odysseus/bin` and reused across downloads. `--continue=true`
means a crashed or aborted download picks up where it left off on restart.
Both directly improve cross-machine reliability.

> *Cookbook error feedback and logging. Failed downloads, dependency installs,
> preflights, and serve jobs should show the actual command/output/error in the
> UI, with copyable logs and clear next steps instead of just "crashed".*

The aria2c progress card in `cookbookRunning.js` surfaces the actual
per-file download state (filename, bytes transferred, percentage, current
speed) live in the UI — not after-the-fact from a log file. `_parseDownloadState`
captures aria2c's structured stdout, so if a file fails the failure is
visible in the card, not buried in a tmux session.

### Known limitation: Windows progress display

The aria2c progress card reads live output via `tmux capture-pane`. On Linux
and macOS this works as expected. On **local Windows**, Odysseus has no tmux —
it uses a detached-process path that writes to a log file instead. Downloads
still complete correctly, but the UI shows a spinner rather than the live card.
Windows remote (SSH into a Windows machine) has the same limitation.

A proper fix would hook the aria2c output into the Windows log-file polling
path rather than capture-pane. That work is deferred; it requires a Windows
test environment to validate. The lock-file `/tmp` hardcode is fixed in this
PR (`tempfile.gettempdir()` on all platforms).

### Note on issue #787 (pause/resume)

Full in-session pause via a UI button is not implemented. What this PR does
add is **resume-on-restart**: aria2c's `--continue=true` flag, combined with
`--auto-file-renaming=false`, means that if the user cancels a download (or
the server crashes, or the connection drops), restarting the same download
picks up from the last completed byte for each file. This covers the core use
case in #787 — a user on a slow connection can stop and continue without
losing progress. A UI pause button remains future work.

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

- **Closes upstream #359** — "Show Download Percentage During Cookbook Downloads"
- **Substantially mitigates upstream #2722** — "Cookbook large HF model downloads
  crash/restart due to SSL ReadError": aria2c has built-in retry (`--retry-wait=3`)
  and resumes partial files (`--continue=true`), so SSL drops no longer abort
  the download from scratch. The reported cache/local-dir confusion is a separate
  concern and not addressed here.
- **Partially addresses upstream #787** — "Add pause and resume functionality":
  resume-on-restart works; in-session pause button is not implemented. The
  description above has full detail.

This PR can be filed independently. `fix/gguf-quality-scored` (#24) is a
companion that adds auto-discovery of GGUF sources for llamacpp models — either
order is fine; they don't depend on each other.
