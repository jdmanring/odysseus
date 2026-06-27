# AI Instructions for Odysseus

This project uses a split-knowledge system to ensure high precision. 
**You MUST read the following files before performing any action:**

1. [docs/ai/RULES.md](./docs/ai/RULES.md) - **CRITICAL**: Hard constraints, the Git pipeline, and "Never" lists.
2. [docs/ai/CONTEXT.md](./docs/ai/CONTEXT.md) - Mental model, architecture, and codebase map.

## Deeper reference (read when a task needs it)

- [docs/ai/non-obvious-behaviors.md](./docs/ai/non-obvious-behaviors.md) - Sharp edges that will bite you: Anthropic tool-result placement, DOM virtualizer invariants, aria2c progress format, tmux width truncation, QWebEngineView API gaps.
- [docs/ai/architecture.md](./docs/ai/architecture.md) - Deep dive on subsystems, request flows, payload building, the Cookbook pipeline, and the native Qt app layer.
- [docs/ai/arch/](./docs/ai/arch/) and [docs/ai/features/](./docs/ai/features/) - Per-flow and per-feature technical reference.
