# AI Rules — Odysseus

> **The Law.** Hard constraints and non-negotiable contribution standards for the
> Odysseus project. Fork workbench operating rules live in `docs/fork/ai-policy.md`.

---

## Core Mandates

**Read the source before writing code.** Find the relevant file, read it, report what
you find. Do not generate code against an assumption about what the code looks like.

**Issue before PR.** Upstream explicitly requires an issue to exist before any PR is
filed. See `CONTRIBUTING.md` for the full policy, including the policy on agent PRs.

**One thing per PR.** No mixing unrelated fixes, formatting changes, or refactors into
a single PR. Each PR must be reviewable in isolation.

**Verify the fix in the running app.** Tests are not sufficient. Before any PR is
considered ready, the fix must be confirmed end-to-end in the actual application.

**Verification Protocol:**
1. **Logs:** Tail the terminal running `app.py` or check `logs/` for tracebacks.
2. **Tests:** Run `pytest tests/[feature_name]` to ensure no regressions.
3. **UI:** Perform the specific user action in the browser that triggered the bug.

**Lifecycle Ownership — Definition of Done:**
A task is not "done" when the code is written; it is done when the entire delivery
chain is complete:
1. **Implementation:** Code is written, linted, and committed to the correct branch.
2. **Verification:** The fix is verified via the Verification Protocol above.
3. **Reporting:** Report the final state and confirm that all tracking is updated.

**Visual changes require screenshots.** Any PR touching `static/js/`, HTML, or CSS
must include a screenshot or clip. See `CONTRIBUTING.md` for details.

**Use existing constants and helpers.** Never hardcode paths, ports, or URLs that
the project already exposes. See `CONTRIBUTING.md` — Code conventions.
