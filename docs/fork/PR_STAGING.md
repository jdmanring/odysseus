# Upstream Contribution Staging Index

This file is the quick-reference index for staged upstream contributions.
Full staging docs (issue + PR templates, ready for copy-paste) are in
`docs/fork/contributions/upstream/`.

**Workflow:** Read `docs/fork/UPSTREAM_CONTRIBUTION_WORKFLOW.md` before filing anything.
The short version: file the issue first, get the number, then open the PR.
**Agents never file upstream issues or PRs directly — James does.**

---

## Upstream Contributions

| # | Title | Type | Issue | PR | Fork Status |
|---|-------|------|-------|----|-------------|
| 01 | HF Token Not Saved Outside Cookbook Tab | Bug | Not filed | Not opened | No fix yet |
| 02 | pytest-timeout Not Declared as Dependency | Bug | Not filed | Not opened | N/A |
| 03 | SearXNG JSON Format Undocumented | Bug/Docs | Not filed | Not opened | Documented internally |
| 04 | realesrgan / basicsr Broken on Python 3.14 | Bug | Not filed | Not opened | Patched via `install-basicsr.sh` |
| 05 | agent_max_tool_calls Defaults to 0 | Bug | Not filed | Not opened | Fixed in `data/settings.json` |
| 06 | Renderer OOM — No DOM Virtualization | Bug | Not filed | Not opened | Stopgap in `linux_wrapper.py`; fix in progress on `fix/dom-oom-virtualization` |
| 07 | streamingTTS ReferenceError in catch Block | Bug | Not filed | Not opened | Fixed in `develop` (commit `9fabdc6`) |
| 08 | Turbo Downloader — Replace hf_transfer with aria2c | Feature | Not filed | Not opened | Implemented in `develop` |

---

## Internal Contributions (Fork-Only)

Tracked in `docs/fork/contributions/internal/`. These are fork-specific improvements
not appropriate for upstream (KDE/Qt integration, Linux native app, sync tooling).

| # | Title | Status |
|---|-------|--------|
| 01 | Native Linux Application (Qt Wrapper) | Active development |
| 02 | QWebEngineView localStorage Persistence | Complete |
| 03 | Upstream Sync Pipeline Tooling | Complete |
