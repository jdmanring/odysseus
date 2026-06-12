# AI Rules — Odysseus

> **The Law.** This document contains hard constraints, the Git pipeline, and non-negotiable policies.

---

## Core Mandates

**Read the source before writing code.** Find the relevant file, read it, report what
you find. Do not generate code against an assumption about what the code looks like.

**No sudo.** If an operation requires elevated privileges, write the command for
the user to run — do not execute it yourself.

**Issue before PR.** Upstream explicitly requires an issue to exist before any PR
is filed. This applies to agent-generated work as well — see `CONTRIBUTING.md` for
the full policy on agent PRs.

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

**Use existing constants and helpers.** Never hardcode paths, ports, or URLs that
the project already exposes. See `CONTRIBUTING.md` — Code conventions.

---

## Rebasing a Feature Branch

When `dev` advances, feature branches need rebasing to apply cleanly on top of current code.

```bash
git log --oneline fix/branch-name..dev | wc -l   # if > 0, rebase needed
git checkout fix/branch-name
git rebase dev
```

**Conflict resolution:** Read both sides. Keep your fix AND incorporate upstream's changes. Remove all conflict markers. `git add <file> && git rebase --continue`.

**If stuck:** `git rebase --abort` to return to pre-rebase state.

## Pre-Flight Checklist (before marking "Ready to File")

- [ ] Branch starts from current `dev`
- [ ] Single clean commit (or tightly related commits)
- [ ] Diff contains only intended files — no unrelated content
- [ ] No hardcoded paths, usernames, or tokens
- [ ] Commit message is clear and written for reviewers
- [ ] `python -m py_compile` passes on changed Python files
- [ ] `node --check` passes on changed JS files
- [ ] Cross-platform considered: no platform-only assumptions in shared code
- [ ] Documentation updated if the change warrants it
