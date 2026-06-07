# [UPSTREAM] Turbo Downloader — Replace hf_transfer with aria2c for Model Downloads

## Status
- Issue filed: Not yet filed
- PR opened: Not yet opened
- Fix in fork: Implemented — `tooling/` on `feat/turbo-downloader` branch (merged to `develop`)

## Notes
This is a feature addition, not a bug fix. Use the Feature Request template on GitHub,
not the Bug Report template.

The implementation lives in `tooling/` on the fork. For the upstream PR, only the
changes relevant to the Cookbook download flow go in — no fork-specific tooling paths.

**What aria2 is:** `aria2c` is a lightweight multi-protocol command-line download
utility available on Linux, macOS, and Windows. It supports opening 16 parallel
connections to a single server, dramatically improving download throughput for large
files (e.g. 70B model weights). It resumes interrupted downloads cleanly. It is
commonly pre-installed on Linux; the `BinManager` class handles auto-install when it
is not. This is the standard approach used by power users to accelerate HuggingFace
downloads — Odysseus can offer it as a first-class option.

**What it replaces:** `hf_transfer` is a Rust-based accelerator for HuggingFace
downloads. It is fast when it works but has known reliability issues: it does not
resume partial downloads, it has platform-specific compilation requirements, and it
produces opaque failures. The current Cookbook already has a `disable_hf_transfer`
retry path, which is evidence that hf_transfer is unreliable enough in practice to
warrant a fallback.

---

## Staged Issue
<!-- James: open https://github.com/pewdiepie-archdaemon/odysseus/issues/new?template=feature_request.yml and paste below -->

**Area:** Cookbook / Local Models / GPU

**Problem or Motivation**

Model downloads through the Cookbook use either `hf_transfer` (Rust accelerator) or
the plain `huggingface-hub` downloader. Both have limitations:

- `hf_transfer` is fast but does not resume interrupted downloads. If a large download
  (e.g. a 70B model at 140 GB) is interrupted by a network drop or system sleep, the
  entire download must restart from zero. It also has compilation requirements that
  fail on some Python versions (e.g. 3.14).
- The plain `huggingface-hub` downloader is single-threaded by default and is
  significantly slower than what the connection can deliver.

The Cookbook already has a `disable_hf_transfer` toggle specifically because
`hf_transfer` is unreliable enough to need a fallback. Neither current option gives
users fast, resumable, reliable downloads out of the box.

**Proposed Solution**

Add `aria2c` as an optional download backend in the Cookbook, invoked when available.
`aria2c` is a mature, multi-platform download utility that:

- Opens 16 parallel connections per file (dramatically faster for large model weights)
- Resumes interrupted downloads automatically via `.aria2` sidecar files
- Is available on Linux, macOS, and Windows (package managers, pre-installed on many
  Linux distros, or auto-downloaded via a `BinManager`-style helper)
- Has no Python compilation dependencies — it is a standalone binary

The implementation:

1. A `BinManager` class that checks for `aria2c` on PATH, and if missing, downloads
   the appropriate platform binary to a local directory (no system install required,
   no root/sudo needed).
2. An `Aria2Wrapper` class that constructs and executes the `aria2c` command with
   the correct flags (`-x 16 -s 16 -c` for max connections and resume).
3. An `HfUrlResolver` class that uses `huggingface-hub`'s API to resolve a repo ID
   to direct `https://huggingface.co/{repo}/resolve/main/{file}` download URLs,
   supporting include-pattern filtering.
4. A download entry point in `cookbook_routes.py` that uses the above when `aria2c`
   is available, with graceful fallback to the existing downloader if not.

**Alternatives Considered**

- `hf_transfer`: fast but non-resumable; existing issues with Python 3.14 and some
  platforms. Already has a known-bad fallback path in the Cookbook.
- Plain `huggingface-hub` `snapshot_download`: reliable but single-threaded.
- `axel`: similar to aria2c but less widely available and less actively maintained.
- `wget`/`curl` with `-c`: resumable but single-connection; much slower for large files.

**Prior Art / Related Issues**

- The existing `disable_hf_transfer` toggle in the Cookbook is direct evidence that
  the current download stack is unreliable enough to need a fallback.
- Power users routinely use `aria2c` manually to download HuggingFace models faster;
  this brings that approach into the UI.

**Willing to implement:** Yes — I can open a PR

---

## Staged PR
<!-- James: file the issue first, get the number, fill in Fixes #NNN below, then open PR -->

### Summary

Model downloads in the Cookbook use `hf_transfer` (non-resumable, platform-sensitive)
or the plain `huggingface-hub` downloader (single-threaded, slow for large weights).
This PR adds `aria2c` as a third option: 16 parallel connections, automatic resume on
interruption, no Python compilation dependencies, works on Linux/macOS/Windows.

When `aria2c` is available on PATH (or installed via the bundled `BinManager`), the
Cookbook download route uses it automatically. If not available, it falls back to the
existing downloader — no regression for any current user.

### Target branch
- [x] This PR targets **`dev`**, not `main`.

### Linked Issue

Part of #

### Type of Change
- [x] New feature (non-breaking — adds new behaviour)

### Checklist
- [x] Searched open issues and open PRs — not a duplicate
- [x] Targets `dev`
- [x] Changes limited to described scope
- [ ] App run locally — model download with aria2c verified end-to-end *(must do before filing)*
- [ ] Fallback to existing downloader verified when aria2c is not available

### How to Test

**With aria2c available:**
1. Install aria2c: `sudo pacman -S aria2` / `brew install aria2` / `apt install aria2`
2. Open Cookbook and download a model (e.g. a small test model).
3. Confirm the download uses aria2c (visible in tmux/terminal output with `-x 16 -s 16`).
4. Interrupt the download mid-way (kill the tmux pane or network disconnect).
5. Re-trigger the download — confirm it resumes from where it stopped.

**Fallback when aria2c is absent:**
1. Remove aria2c from PATH (rename the binary temporarily).
2. Trigger a Cookbook download.
3. Confirm it falls back to the standard `hf download` / `snapshot_download` path
   without error.

### Visual / UI changes

The download flow runs in a tmux pane — the visible output changes (aria2c's progress
display vs. hf's). Attach a screenshot of the Cookbook with an active aria2c download
in the terminal pane if the PR includes any UI text changes (e.g. "Downloading with
aria2c…" status messages).

- [ ] Screenshot of active aria2c download in Cookbook terminal pane *(attach if UI text changes)*
