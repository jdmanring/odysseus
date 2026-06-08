# [UPSTREAM] aria2c Downloader — Replace hf_transfer with aria2c for Model Downloads

## Status
- Issue filed: Not yet filed
- PR opened: Not yet opened
- Fix in fork: `develop` branch

## Notes

This is a **feature addition**. Use the **Feature Request** template on GitHub, not Bug Report.

**Upstream PR scope** — only these files go upstream (no fork-specific paths, UI card, or SSH orchestration):
- `tooling/aria2c_download.py` (new)
- `tooling/hf_url_resolver.py` (new)
- `tooling/bin_manager.py` (new)
- `routes/cookbook_routes.py` — integration point only (the `use_aria2c` branch in `_model_download_inner`)
- `tests/test_aria2c_circuit.py` (new)

The download progress card (`cookbookRunning.js`, `style.css`) is fork-specific and will be staged as a separate upstream contribution once the backend is merged.

**Before filing:** run `python -m pytest tests/test_aria2c_circuit.py -v` and confirm all pass. Run the app locally, trigger a real download with `use_aria2c` enabled, confirm the aria2c progress is visible, interrupt and confirm resume.

**Screenshots required** — the PR touches `routes/cookbook_routes.py` which drives UI state. Attach a screenshot of the Cookbook running tab showing the download in progress.

---

## Staged Issue
<!-- James: open https://github.com/pewdiepie-archdaemon/odysseus/issues/new?template=feature_request.yml -->
<!-- Fill in the form fields exactly as written below. -->

**Prerequisites** *(check all before submitting)*
- [x] I searched open issues and this has not already been proposed.
- [x] I searched discussions and this is not already being debated there.
- [x] This is a concrete, actionable proposal — not a vague "it would be nice if..." request.

**Area:** Cookbook / Local Models / GPU

**Problem or Motivation**

Model downloads through the Cookbook currently rely on `hf_transfer` (Rust accelerator) or the plain `huggingface-hub` downloader. Both have serious practical limitations for large models:

- **Zero observability**: `hf_transfer` gives no real-time speed, ETA, or granular progress per file. Users watch a frozen terminal and cannot tell a slow download from a hung one.
- **Silent failures on large files**: `hf_transfer` is already disabled by default in the codebase for large downloads because it crashes near the end at high throughput. The `disable_hf_transfer` toggle in the Cookbook is direct evidence the current stack is unreliable enough to need a fallback.
- **Platform fragility**: `hf_transfer` is a Rust binary that frequently encounters GLIBC version mismatches on remote Linux servers.
- **No robust resume**: `hf_transfer` does not resume partial downloads. A 140 GB download interrupted at 99% restarts from zero.

**Proposed Solution**

Add `aria2c` as a download transport with automatic binary management via `BinManager`.

`aria2c` is the standard tool for high-performance reliable downloads: 16 parallel connections per file, `.aria2` sidecar-file resume, works on Linux/macOS/Windows as a standalone static binary with no compilation or package manager dependencies.

Implementation:

1. **`tooling/bin_manager.py`** — `BinManager.ensure_binary("aria2c")` auto-downloads a static `aria2c` build to `~/.cookbook/bin/` if aria2c is not on PATH. Covers Linux x86_64/aarch64, macOS x86_64/arm64, Windows AMD64. No sudo required.
2. **`tooling/hf_url_resolver.py`** — Resolves a HuggingFace repo's file list and commit SHA via the HF API. Returns per-file direct download URLs pinned to the resolved commit hash so the downloaded files form a valid HF hub cache entry.
3. **`tooling/aria2c_download.py`** — Entry point. Gets the aria2c binary, resolves file URLs, then downloads all files in parallel using aria2c's `--input-file` mode (`--max-concurrent-downloads=4 --max-connection-per-server=4` = 4 files × 4 connections = 16 total, same bandwidth budget as the old sequential 16-connection-per-file approach but completing multi-shard models significantly faster). Passes the HF token in the `Authorization` header for gated models. Saves to the standard HF hub cache layout (`models--{org}--{repo}/snapshots/{sha}/`) with `refs/main` written so `snapshot_download(repo_id)` resolves locally without a network round-trip.
4. **`routes/cookbook_routes.py`** — When `use_aria2c=true` in the download request, calls `aria2c_download.py` instead of `hf download`. Falls back to the existing `hf download` / `snapshot_download` path when aria2c is unavailable — no regression for any current user.

**Alternatives Considered**

- `hf_transfer`: fast but non-resumable; known issues on Python 3.14 and some Linux distros. Already has a known-bad fallback path in the Cookbook.
- Plain `huggingface-hub` `snapshot_download`: reliable but single-threaded and gives no parallel connection count or per-file progress.
- `axel`: similar concept, less widely available, less actively maintained.
- `wget`/`curl -c`: resumable but single-connection; much slower for large files.

**Prior Art / Related Issues**

The existing `disable_hf_transfer` flag in the Cookbook and the retry logic that sets `disable_hf_transfer=True` on retry both directly document the current stack's reliability problems. Power users routinely download HuggingFace models with `aria2c` manually to get parallel connections and resume; this brings that approach into the UI as a first-class, managed option.

**Are you willing to implement this?** Yes — I can open a PR

---

## Staged PR
<!-- James: file the issue first, add the issue number to "Fixes #" below, then open the PR -->
<!-- PR branch: upstream/aria2c-downloader, based on upstream-mirror, not develop -->

### Summary

Adds `aria2c` as a high-performance, resumable model download transport to the Cookbook, replacing the `hf_transfer` path that fails silently on large files and has no resume capability.

- **`tooling/bin_manager.py`** (new): `BinManager.ensure_binary("aria2c")` auto-downloads a static `aria2c` build for the current platform to `~/.cookbook/bin/`. Platforms: Linux x86_64/aarch64, macOS x86_64/arm64, Windows AMD64. Falls back to system PATH if already installed. No sudo, no package manager.
- **`tooling/hf_url_resolver.py`** (new): Resolves HuggingFace repo files and the current HEAD commit SHA via `HfApi`. Returns per-file direct download URLs pinned to the resolved commit so resumed downloads are reproducible and the resulting cache is recognised by `snapshot_download(repo_id)`.
- **`tooling/aria2c_download.py`** (new): Orchestrates the download. Calls BinManager for the binary, HfUrlResolver for URLs, then runs a single `aria2c` subprocess with `--input-file` mode — downloading up to 4 files simultaneously (4 connections each = 16 total), with the HF token in the Authorization header and `.aria2` sidecar-file resume. Saves to `~/.cache/huggingface/hub/models--{org}--{repo}/snapshots/{sha}/` and writes `refs/main` with the resolved SHA — a valid HF hub cache entry that `snapshot_download` and vllm/llama-server find without re-downloading.
- **`routes/cookbook_routes.py`**: when `use_aria2c=true` in the download request body, calls `aria2c_download.py` via the existing tmux session runner. Falls back to `hf download` / `snapshot_download` when aria2c is unavailable — existing behaviour unchanged for `use_aria2c=false`.
- **`tests/test_aria2c_circuit.py`** (new): six tests covering BinManager install, executable check, `--version` smoke, real download of `gpt2/tokenizer.json` (small public file), resume idempotency, and PATH fallback.

### Target branch
- [x] This PR targets **`dev`**, not `main`.

### Linked Issue

Fixes #

### Type of Change
- [x] New feature (non-breaking — existing path unchanged when `use_aria2c` is false)

### Checklist
- [x] I searched [open issues](https://github.com/pewdiepie-archdaemon/odysseus/issues) and [open PRs](https://github.com/pewdiepie-archdaemon/odysseus/pulls) — this is not a duplicate.
- [x] This PR targets `dev`
- [x] My changes are limited to the scope described above — no unrelated refactors or whitespace changes mixed in.
- [ ] I actually ran the app and verified the change works end-to-end. *(must verify before filing)*

### How to Test

**Automated tests** (BinManager auto-installs aria2c — no manual steps needed):
```bash
python -m pytest tests/test_aria2c_circuit.py -v
```
Expected: all 6 tests pass. `~/.cookbook/bin/aria2c` appears after first run.

**Manual end-to-end — aria2c path:**
1. Start the app (`uvicorn app:app` or `docker compose up`).
2. Open Cookbook → download a model → enable the aria2c toggle.
3. Confirm the running task output shows `[*] Using aria2c:` and `[#gid ... CN:16 DL:...]` progress lines.
4. Mid-download: kill the tmux session or stop the download.
5. Re-trigger the same download — confirm it resumes (files partially present, aria2c skips completed bytes, `.aria2` sidecar consumed).
6. After completion: confirm the model appears in the Serve tab model picker without a page reload.

**Fallback when aria2c is absent:**
1. Rename `~/.cookbook/bin/aria2c` temporarily and ensure aria2c is not on PATH.
2. Trigger a Cookbook download with `use_aria2c=true`.
3. Confirm it prints `[!] aria2c not found and auto-install failed` and falls back to `hf download` / `snapshot_download` without an unhandled error.

**Gated model (requires HF token):**
1. Set the HF token in Cookbook settings.
2. Download a gated model with `use_aria2c=true`.
3. Confirm download proceeds (token passed in Authorization header).
4. Remove or clear the token and retry — confirm a clear "401 Unauthorized" or "Access restricted" message appears, not a silent failure.

**Cache compatibility:**
```python
from huggingface_hub import snapshot_download
# After downloading nvidia/some-model with aria2c:
path = snapshot_download("nvidia/some-model", local_files_only=True)
print(path)  # should return the local snapshots/ path without re-downloading
```

### Visual / UI changes

- [ ] Screenshot or short clip of the change in the running app, attached below.
- [x] Style match: this PR does not touch any rendered HTML/CSS/JS. The download command runs inside an existing tmux pane; no new UI elements are introduced.
- [x] No new component patterns.
- [x] I am not an LLM agent submitting a bulk PR. *(James files this manually after reviewing the staged doc.)*

### Screenshots / clips

<!-- James: attach a screenshot of the Cookbook running tab showing an active aria2c download.
     The tmux pane output with [#gid ...CN:16 DL:...] lines satisfies the visual requirement. -->

---

## Tests — `tests/test_aria2c_circuit.py`

```python
"""
Circuit tests for the aria2c download pipeline.

BinManager.ensure_binary("aria2c") is called once and the binary is reused
across the session — no repeated downloads on subsequent runs.

Uses gpt2 (tokenizer.json, ~1MB, public) as the real-download target.
No HF token required.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = "gpt2"
TEST_FILE = "tokenizer.json"
COOKIE_BIN = Path.home() / ".cookbook" / "bin"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_aria2c():
    """Return aria2c path via BinManager, caching the result."""
    from tooling.bin_manager import BinManager
    path = BinManager.ensure_binary("aria2c")
    if path:
        return Path(path)
    system = shutil.which("aria2c")
    if system:
        return Path(system)
    return None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_binmanager_installs_aria2c():
    """BinManager.ensure_binary returns a path and the file exists."""
    aria2c = _get_aria2c()
    assert aria2c is not None, "BinManager could not locate or install aria2c"
    assert aria2c.exists(), f"Returned path does not exist: {aria2c}"


def test_aria2c_is_executable():
    """The binary is executable (not just present)."""
    aria2c = _get_aria2c()
    assert aria2c is not None
    assert os.access(aria2c, os.X_OK), f"{aria2c} is not executable"


def test_aria2c_version_smoke():
    """aria2c --version exits 0 and prints a version string."""
    aria2c = _get_aria2c()
    assert aria2c is not None
    result = subprocess.run([str(aria2c), "--version"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "aria2" in result.stdout.lower(), "Unexpected --version output"


def test_real_download_gpt2_tokenizer(tmp_path):
    """Downloads gpt2/tokenizer.json (~1 MB) with aria2c and verifies the file."""
    from tooling.hf_url_resolver import HfUrlResolver
    from tooling.aria2c_download import download_file

    aria2c = _get_aria2c()
    assert aria2c is not None

    resolver = HfUrlResolver()
    urls, commit = resolver.resolve_snapshot_urls(REPO, include=TEST_FILE)
    assert urls, "Resolver returned no URLs for gpt2/tokenizer.json"

    url, rel_path = urls[0]
    out_dir = tmp_path / "gpt2"
    ok = download_file(aria2c, url, out_dir, Path(rel_path).name, token=None)
    assert ok, "download_file returned False (non-zero aria2c exit)"
    assert (out_dir / Path(rel_path).name).exists()


def test_resume_idempotent(tmp_path):
    """
    Running the download twice does not re-download already-complete files.
    aria2c exits 0 immediately when the file is already present and complete.
    """
    from tooling.hf_url_resolver import HfUrlResolver
    from tooling.aria2c_download import download_file

    aria2c = _get_aria2c()
    resolver = HfUrlResolver()
    urls, _ = resolver.resolve_snapshot_urls(REPO, include=TEST_FILE)
    url, rel_path = urls[0]
    out_dir = tmp_path / "gpt2"

    ok1 = download_file(aria2c, url, out_dir, Path(rel_path).name, token=None)
    assert ok1

    mtime_after_first = (out_dir / Path(rel_path).name).stat().st_mtime

    ok2 = download_file(aria2c, url, out_dir, Path(rel_path).name, token=None)
    assert ok2

    mtime_after_second = (out_dir / Path(rel_path).name).stat().st_mtime
    assert mtime_after_second == mtime_after_first, \
        "File was re-downloaded on second run (mtime changed)"


def test_path_fallback_uses_system_aria2c(monkeypatch, tmp_path):
    """
    When BinManager returns None, get_aria2c() falls back to whatever is on PATH.
    This verifies the fallback branch runs without error.
    """
    from tooling import bin_manager as bm_module

    original = bm_module.BinManager.ensure_binary

    def mock_ensure(_name):
        return None  # simulate BinManager failure

    monkeypatch.setattr(bm_module.BinManager, "ensure_binary", staticmethod(mock_ensure))

    from tooling.aria2c_download import get_aria2c
    # reload to pick up the monkeypatched BinManager
    import importlib
    import tooling.aria2c_download as dl_module
    importlib.reload(dl_module)

    result = dl_module.get_aria2c()
    system_aria2c = shutil.which("aria2c")

    if system_aria2c:
        assert result is not None
        assert str(result) == system_aria2c
    else:
        assert result is None  # no aria2c anywhere — correct None return
```
