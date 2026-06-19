# Odysseus Fork Onboarding Documentation

This document provides an overview of the Odysseus fork (`jdmanring/odysseus`) and serves as a guide for understanding its purpose, structure, and contribution workflow.

## Purpose of This Fork

This fork is a **contribution workbench**, not a divergent product. Its purpose is to:
- Develop and stage upstream pull requests to `pewdiepie-archdaemon/odysseus`
- Test and verify fixes/features before submitting them upstream
- Maintain a clean separation between fork-specific workbench features and upstream-candidate code

**Default assumption**: Every fix, feature, and document is upstream-candidate unless it specifically manages the fork/upstream relationship (e.g., sync pipeline, fork CI, fork management documentation).

## Repository Structure

### Key Directories
- `/docs/fork/` - Fork-specific documentation and management hub
- `/docs/ai/` - AI context, rules, and procedures for the Odysseus project
- `/docs/project/` - Technical architecture and non-obvious behaviors
- `/docs/user/` - User guides and workflow documentation
- `/tooling/` - Critical utilities (aria2c downloader, binary manager, HF URL resolver)
- `/mcp_servers/` - MCP server implementations
- `/src/` - Core business logic
- `/routes/` - API route handlers
- `/static/` - Frontend SPA (no bundler, plain ES modules)

### Important Files
- `qt_wrapper.py` - Native Linux Qt application wrapper
- `tooling/aria2c_download.py` - HuggingFace model downloader via aria2c
- `tooling/hf_url_resolver.py` - HF signed URL resolver
- `tooling/bin_manager.py` - Automatic binary installation utility
- `docs/fork/ai-policy.md` - Fork-specific operating rules
- `docs/ai/RULES.md` - Core contribution standards and verification protocols
- `docs/fork/upstream/` - Upstream PR tracking and staging areas

## Git Workflow Remotes

This fork uses two remotes:
- `origin` - `github.com/jdmanring/odysseus` (read/write - development target)
- `upstream` - `github.com/pewdiepie-archdaemon/odysseus` (read-only - source project)

**Critical Rules**:
- Never push to the `upstream` remote
- Never file issues or PRs on upstream without explicit authorization
- Always stage work in `docs/fork/upstream/pr-drafts/` before considering upstream submission
- Fork-specific branches start from `develop`; upstream-candidate branches start from `upstream-mirror`

## Development Workflow

### Branch Creation
1. Create tracking issue on `jdmanring/odysseus`
2. Create branch from correct base:
   - Upstream-candidate work: `git checkout -b fix/description upstream-mirror`
   - Fork-only work: `git checkout -b fix/description develop`
3. Do work, commit with descriptive message referencing issue
4. Cherry-pick to `develop` to make fix live in working branch

### Ingesting Upstream Changes
When new commits appear in `upstream/dev`:
```bash
git checkout integration
python3 tooling/sync-upstreams/upstream_ingest_pipeline.py --skip-tests
git checkout develop
git merge integration
```

### Rebasing Staging Branches
Before filing PR upstream:
```bash
git checkout fix/branch-name
git rebase upstream-mirror
# Resolve conflicts by keeping both our fix and upstream's changes
```

## Verification Protocol (Definition of Done)

Before considering any work complete:
1. **Implementation**: Code written, linted, committed to correct branch
2. **Verification**: 
   - Check logs for tracebacks
   - Run relevant tests (`pytest tests/[feature_name]`)
   - Perform specific user action in browser to confirm fix
3. **Reporting**: 
   - Update fork tracking documents (PR draft, active-work.md, pr-status.md, changes-from-upstream.md)
   - Confirm all tracking is current
   - Close issue only after verification

## Non-Obvious Behaviors to Know

### Frontend
- No bundler: new `.js` files need `<script>` tag in `index.html`
- Model picker autohides after 10 non-whitespace characters (intentional)
- Plan window only updates when `update_plan` is explicitly called
- DOM virtualization in `chatHistory.js` - preserve `window.chatHistory.reset()` on session switches

### Native Linux App (`qt_wrapper.py`)
- Wrapper owns server lifecycle - don't run uvicorn separately
- `QWebEngineView` is Chromium but not a browser - Web EyeDropper API missing
- External links must route through `OdysseusPage` to system browser
- Hardcoded profile path: `~/.local/share/odysseus/webengine`

### Downloads (aria2c)
- HF signed URLs expire - never cache resolved URLs
- `_dlFileTracker` is module-level state - persists across poll ticks
- aria2c progress format has leading space: `^\s*\[#` not `^\[#`
- TMUX width fix needed: `-x 220 -y 50` for FILE: output
- Capture pane scrollback limit - use `let totalFiles` fallback to tracker

### Backend / LLM
- Anthropic tool results must stay inline (don't collapse into system prompt)
- `data/settings.json` overrides `src/settings.py` DEFAULT_SETTINGS
- Agent tool budget defaults to 20 (`agent_max_tool_calls`)

## Communication Channels

- Issues and discussions: Use GitHub issues on `jdmanring/odysseus` fork
- Upstream coordination: Follow procedures in `docs/fork/ai-policy.md`
- Documentation updates: Keep `docs/fork/` synchronized with actual workflow

## Getting Started

1. Clone the fork: `git clone git@github.com:jdmanring/odysseus.git`
2. Set up environment: `cp .env.example .env` and configure as needed
3. Start development: `docker compose up -d --build` or run `qt_wrapper.py` for native app
4. Access UI: `http://localhost:7000` (Docker) or native Qt window
5. First admin password: printed in container logs (`docker compose logs odysseus`)

## Contributing

Refer to:
- `docs/ai/RULES.md` - Core contribution standards
- `docs/fork/ai-policy.md` - Fork-specific operating rules
- `CONTRIBUTING.md` (upstream) - General contribution guidelines
- `ROADMAP.md` - Project direction and planned features

Remember: The goal is to contribute improvements back to upstream. Keep fork-specific work minimal and well-documented.
