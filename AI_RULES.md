# Odysseus — AI Agent Instructions

Odysseus is a self-hosted AI workspace: FastAPI backend, plain-JS frontend, SQLite +
ChromaDB storage. Runs locally at `127.0.0.1:8000`. Read `CONTRIBUTING.md` for the
full contribution rules. Key points for AI agents are summarized below.

---

## Rules

**Read the source before writing code.** Find the relevant file, read it, report what
you find. Do not generate code against an assumption about what the code looks like.

**No sudo.** If an operation requires elevated privileges, write the command for the
user to run — do not execute it yourself.

**Issue before PR.** Upstream explicitly requires an issue to exist before any PR is
filed. This applies to agent-generated work as much as human work — see `CONTRIBUTING.md`
for the full policy on agent PRs.

**One thing per PR.** No mixing unrelated fixes, formatting changes, or refactors into
a single PR. Each PR must be reviewable in isolation.

**Verify the fix in the running app.** Tests are not sufficient. Before any PR is
considered ready, the fix must be confirmed end-to-end in the actual application.

**Verification Protocol:**
1. **Logs:** Tail the terminal running `app.py` or check the `logs/` directory for tracebacks.
2. **Tests:** Run `pytest tests/[feature_name]` to ensure no regressions.
3. **UI:** Perform the specific user action in the browser that triggered the bug.

**Visual changes require screenshots.** Any PR touching `static/js/`, HTML, or CSS
must include a screenshot or clip. See `CONTRIBUTING.md` for details.

**Use existing constants and helpers.** Never hardcode paths, ports, or URLs that the
project already exposes. See `CONTRIBUTING.md` — Code conventions.

## Working Style

- State what you are about to do before making non-trivial changes.
- Keep responses concise. No trailing summaries restating what the diff already shows.
- No speculative files — don't create planning docs, analysis notes, or scaffolding
  unless explicitly asked.

---

## Fork-Specific Rules (jdmanring/odysseus only)

The following rules apply only when working in this fork. They have no meaning in the
upstream source project.

- **Never push to the `upstream` remote** or file issues/PRs there without James's
  explicit per-action authorization. Agents stage work on clean branches; James files the PRs.
- **Never commit to `upstream-mirror`.** This branch is reset-only; any commits are lost on next sync.
- **Never cherry-pick upstream → `develop` directly.** Use the sync pipeline:
  `tooling/sync-upstreams/upstream_ingest_pipeline.py` → promotes to `integration` → merge to `develop`.
- **Branch origin matters.** Upstream-candidate branches must start from `upstream-mirror`, not `develop`.
  Fork-only branches start from `develop`. Getting this wrong contaminates upstream PRs with fork history.
  Full rules: `docs/dev/git-branch-workflow.md`.
- **Never close issues without verification.** An issue is closed only when the fix is confirmed working.
- **Fork docs:** `AI_CONTEXT.md` (code mental model), `docs/fork/active-work.md`
  (current branch status), `docs/fork/issue-tracker.md` (open issues and branches),
  `docs/dev/git-branch-workflow.md` (full pipeline + branch procedure).
