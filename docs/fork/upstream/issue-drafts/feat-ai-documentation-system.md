# Upstream Issue Draft: feat-ai-documentation-system

**File on:** `odysseus-dev/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/feat-ai-documentation-system.md`
**Branch:** `feat/ai-documentation-system`
**Type:** Enhancement / Documentation

---

## Title

`[Docs] Add AI-first documentation system: CONTEXT.md, RULES.md, per-feature references, architecture and contributor guides`

---

## Body

**Area:** Documentation

**Problem / Motivation:**
Odysseus has no structured documentation for AI coding assistants, new contributors, or anyone trying to understand the codebase without reading all of the source. Critical behaviors are implicit: the agent loop, tool execution, session/vault architecture, the Cookbook pipeline, the Qt wrapper layer. There is no standard entry point for AI agents, no per-feature technical reference, no architecture overview, and no contributor guide covering common task patterns. Contributors, human or AI, orient themselves entirely through source code reading and trial and error.

**Proposed Solution:**
A complete hub-and-spoke documentation layer. All files are new; no existing files are modified.

**Root level**
- `AI.md`: universal entry point for AI agents: directs them to rules and context, explains what each doc covers

**`docs/ai/`: AI reference documentation**
- `RULES.md`: behavioral rules for AI coding assistants (hard rules around destructive operations, upstream contribution policy, issue tracking)
- `CONTEXT.md`: mental model of the codebase: architecture, subsystem map, key files, common task patterns
- `arch/AI_ARCH_CORE_FLOW.md`: core request/response flow
- `features/` (20 files): per-feature technical reference for Cookbook, Brain/orchestration, Calendar, Codex, Compare, Contacts, Deep Research, Email, Gallery, Notes, Skills/MCP, STT/TTS, Tasks, Theme, Tools, Vault, and YouTube
- `system/`: secrets storage patterns, settings key map

**`docs/project/`: technical tribal knowledge**
- `architecture.md`: deep-dive on subsystems, request flows, payload building, the Cookbook pipeline, and the native Qt layer
- `non-obvious-behaviors.md`: sharp edges that will surprise contributors: DOM virtualizer invariants, aria2c regex format, tmux truncation, Anthropic tool result placement, QWebEngineView browser API gaps

**`docs/user/`: user-facing guides**
- `interface_ui_map.md`, `user_journeys_workflows.md`, `cookbook_lifecycle.md`, `plan_sync_guide.md`, `ux_tips.md`

**`docs/dev/`: contributor guides**
- `documentation_templates.md`, `lessons_learned.md`, `local-setup-and-running.md`

36 new files total.

**Alternatives Considered:**
- Inline code comments: cover narrow cases but do not provide cross-cutting architectural context or agent-readable behavioral rules.
- GitHub wiki: requires separate maintenance outside the repo and does not stay in sync with the codebase automatically.
- Files in the repo are versioned alongside the code and naturally stay current as the codebase evolves.
