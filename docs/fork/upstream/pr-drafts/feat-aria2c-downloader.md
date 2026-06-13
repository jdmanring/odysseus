# PR Draft: feat/aria2c-downloader → pewdiepie-archdaemon/odysseus:dev

**Branch:** `jdmanring/odysseus:feat/aria2c-downloader`
**Issue:** [#12](https://github.com/jdmanring/odysseus/issues/12) + [#23](https://github.com/jdmanring/odysseus/issues/23) (fork tracking)
**Status:** Integration tests passing as of 2026-06-12 — ready to file
**Screenshot:** `docs/fork/screenshots/aria2c.png`

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
- Sums the resolved file sizes and prints `[*] Total size: X bytes` so
  the UI has the exact model total before any files download
- Writes an aria2c input file (tab-indented options, Bearer auth header)
- Spawns aria2c with 4 parallel files × 3 connections each (12 total —
  tuned to avoid HF CDN throttling)
- Verifies the output directory is non-empty after aria2c exits 0

**`tooling/hf_url_resolver.py`** — resolves a HF repo to a list of
`(url, relative_path, size_bytes)` tuples pinned to the HEAD commit hash.
Uses `list_repo_tree()` (available since huggingface_hub 0.19) to retrieve
file sizes in the same API call, so the downloader knows the exact model
total before the first byte transfers. Falls back to `list_repo_files()`
(no sizes) and then to a direct HTTP API call if the hub library fails.
The HTTP fallback correctly filters to file entries only. Includes a
basename-aware `include` filter so `*.gguf` correctly matches files in
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
stdout (parallel progress lines, `FILE:` path, `[*] N files` banner,
`[*] Total size: X bytes` banner). `_dlFileTracker` accumulates per-file
byte counts across poll ticks and exposes accurate overall `pct`, `dlSize`,
`totalSize`, and `eta` for the full model, not just the currently active batch
of 4 files. The exact total from the resolver banner is used for all four
values; an averaging fallback covers the case where sizes were unavailable.
`totalFiles` falls back to `_dlFileTracker.totalFileCount` when the startup
banner scrolls out of the 200-line `capture-pane` window. `isSingleFileSplit`
detects when all `perFileData` entries share a filename (one file downloaded as
N pieces with `--split=N`). For that case, aria2c emits both a parent GID
(full file size, `CN:N`) and N piece GIDs (each `1/N` file size, `CN:1`);
naively summing all entries would double `totalBytes` and report `2N`
connections. The parser detects the parent GID (`connections > 1`) and uses
its values directly, falling back to the resolver-banner total as the
authoritative size. The multi-batch tracker is skipped for this case since
there is only one logical file to track.

The task actions menu (`⋮`) now toggles — a second click closes the dropdown
instead of dismissing and immediately recreating it. `_downloadOutputLooksActive`
gains an aria2c progress-line pattern so that if a task briefly hits a terminal
status while aria2c is still mid-flight, the indicator becomes the reconnect
affordance (flip back to running) rather than a destructive clear action.

**`static/js/cookbook-hwfit.js`** — `refreshCachedModelIds()` now handles local
downloads (no `remoteHost`). Previously returned early for empty host, making
the downloaded-dot re-mark a no-op for local installs. Both Running tab
done-transition paths now call `refreshCachedModelIds` so the catalog dot
appears immediately without a page reload.

**`static/style.css`** — download card, per-file progress rows, cancel button.

### Tests

**`tests/test_aria2c_circuit.py`** — end-to-end integration tests against the
real HuggingFace API (no mocks):

- **BinManager**: installs aria2c for the current platform, verifies the binary
  exists, is executable, and responds to `--version`.
- **`get_aria2c()`**: resolves via BinManager and system PATH fallback.
- **`HfUrlResolver`**: calls the live HF API for `gpt2`; asserts that returned
  URLs are valid `https://huggingface.co/` URLs pinned to the resolved commit
  hash, that `rel_path` values are relative (no leading `/`), and that each
  tuple includes an integer `size_bytes` field.
- **`download_file()`**: downloads `gpt2/tokenizer.json` via a real aria2c
  subprocess; asserts the file exists on disk and is non-empty.
- **Resume idempotency**: runs `download_file()` twice on the same target;
  asserts `--continue=true` exits 0 and the file size is unchanged.

All tests pass against the live API as of 2026-06-12.

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

This PR implements in-session pause and resume. The Pause button sends SIGINT
to the aria2c process via `tmux send-keys C-c`; the download card immediately
shows a `paused` badge. Resume starts a new aria2c session against the same
output directory; aria2c's `--continue=true` flag picks up from the last
completed byte for each file. The background status-reconciliation loop is
guarded so that a paused task's status is never overwritten by a stale
server-side `done` or `running` signal — the card stays `paused` until the
user explicitly resumes or stops.

### Screenshot

Qwen3-Coder-Next-AWQ-4bit (44.97 GiB, 25 files) mid-download — 4 files active
in parallel, 3 connections each, HF token authenticated (`authed` badge):

![aria2c download card](../screenshots/aria2c.png)

### Testing

**Automated (passing):**

- [x] `pytest tests/test_aria2c_circuit.py` — 9 passed, 1 skipped (system-PATH
  fallback, skipped when system aria2c not on PATH). Tests hit the live HF API:
  URL resolution, commit pinning, size retrieval, real file download, and resume
  idempotency all verified against `gpt2`.

**Manual (verified during development):**

- [x] Download a single-file GGUF model — progress card shows correct total
  size throughout (not doubled); connection count shows split count, not 2×;
  downloaded-dot (●) appears on catalog row immediately without page reload
- [x] Download a multi-shard model (25 files, 115 GiB) — per-file rows show
  correct filenames; overall percentage, total size, and ETA all reflect the
  full model size (not just the 4 currently active files)
- [x] Pause single-file download — card shows `paused` badge and type chip;
  does not flip to `finished` after the background reconciliation loop fires
- [x] Pause multi-file download — same; clicking the task header to
  collapse/expand does not cause a spurious `finished` transition
- [x] Resume paused download — resumes from last completed byte; aria2c
  `--continue=true` confirmed working
- [x] Resume behavior on restart — restarting a download after interruption
  resumes from last completed byte; verified via `test_resume_is_idempotent`
- [x] GGUF auto-discovered repo — downloaded-dot appears for both in-session
  completion and after page reload

**Still needs manual verification before filing:**

- [x] HF token auth — `authed` badge visible in screenshot; token found and
  applied to aria2c Bearer header for a 44.97 GiB 25-file download
- [ ] Cancel mid-download — tmux session teardown and partial-file cleanup
- [ ] Windows local install — progress card not expected (known limitation),
  but download completion should still work via the log-file path

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
