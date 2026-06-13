# PR Draft: feat/ai-documentation-system → pewdiepie-archdaemon/odysseus:dev

**Branch:** `jdmanring/odysseus:feat/ai-documentation-system`
**Issue:** [#18](https://github.com/jdmanring/odysseus/issues/18) (fork tracking)
**Status:** Ready to file

---

## Title

`docs: AI-first documentation system — universal hub-and-spoke onboarding and reference guides`

---

## Description

### Problem

Odysseus has no structured documentation for contributors or AI agents trying
to understand the codebase. Critical behaviors are implicit and discovered
only by reading source code or through trial and error. There is also no
standard way for AI coding assistants to orient themselves to the project.

### Solution

A complete documentation layer covering AI agent context, system architecture,
per-feature technical references, and contributor guides, utilizing a universal
hub-and-spoke model for maximum agent precision.

### Root level

**`AI.md`** — The universal entry point for AI agents. A root-level index that
directs agents to the authoritative laws and maps of the project.

### `docs/ai/` — AI reference documentation

**`RULES.md`** — Behavioral rules for AI agents contributing to the project.
Platform-agnostic. Covers hard rules around destructive operations, upstream
contribution policy, and issue tracking.

**`CONTEXT.md`** — Mental model of the codebase for AI agents. Covers the
architecture, subsystem map, key files, and common task patterns.

**`arch/AI_ARCH_CORE_FLOW.md`**: core request/response flow
**`features/`** (20 files): per-feature technical reference covering Cookbook,
  Brain/orchestration, Calendar, Codex, Compare, Contacts, Deep Research,
  Email, Gallery, Notes, Skills/MCP, STT/TTS, Tasks, Theme, Tools, Vault,
  and YouTube
**`system/`**: secrets storage patterns and the settings key map

### `docs/project/` — technical tribal knowledge

**`architecture.md`** — deep-dive on subsystems, request flows, payload
building, the Cookbook pipeline, and the native Qt app layer.

**`non-obvious-behaviors.md`** — sharp edges that will surprise contributors:
DOM virtualizer invariants, aria2c regex format, tmux terminal width truncation,
Anthropic tool result placement requirements, QWebEngineView browser API gaps,
and more.

### `docs/user/` — user-facing guides

`interface_ui_map.md`, `user_journeys_workflows.md`, `cookbook_lifecycle.md`,
`plan_sync_guide.md`, `ux_tips.md`

### `docs/dev/` — contributor guides

`documentation_templates.md`, `lessons_learned.md`, `local-setup-and-running.md`

### Files Added

36 new files. No existing files modified.

### How to Test

1. After merging, open `AI.md` at the repo root on GitHub — confirm it renders correctly and links to `docs/ai/CONTEXT.md` and `docs/ai/RULES.md`.
2. Navigate to `docs/ai/CONTEXT.md` — confirm headers, code blocks, and internal links render.
3. Open two or three files from `docs/ai/features/` — confirm each covers its feature area and renders without broken formatting.
4. Run a link check if available: `find docs/ai -name "*.md" -exec grep -l "\[.*\](.*\.md)" {} \;` and spot-check that the linked files exist.
5. No runtime behavior changes — no server restart required.

---

## Filing Notes

This PR has no dependencies and can be filed in any order. It adds only new
files and does not modify any existing code or documentation.
