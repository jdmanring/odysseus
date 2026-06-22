# PR Draft: fix/skill-lifecycle-correctness → pewdiepie-archdaemon/odysseus:dev

**Branch:** `jdmanring/odysseus:fix/skill-lifecycle-correctness`
**Issue:** [#86](https://github.com/jdmanring/odysseus/issues/86)
**Base:** `upstream-mirror` (latest upstream commit)
**Status:** Ready to file

---

## Title

`fix(skills): correct auto_approve_skills semantics — extraction always draft, audit defaults to promote`

---

## Summary

### Problem

Four bugs in `auto_approve_skills` pref handling break the autonomous skill cultivation pipeline:

1. **Extraction (`skill_extractor.py:~274`)**: pref check with `True` default auto-publishes extracted skills immediately — before the audit tests them. A skill from a failed or non-representative session becomes active agent context instantly.

2. **Injection gate (`agent_loop.py:~1231`)**: `min_conf=2.0` blocks ALL drafts when `auto_approve=False`. Teacher-escalation drafts (confidence=0.9) fail the gate and never inject. The SkillWeaver teacher→student transfer pattern (strong model helps weak model retry) requires teacher drafts to inject immediately — this is silently broken (arxiv:2504.07079, +54.3% task success).

3. **Audit promotion (`skills_routes.py:~504`)**: upstream already had `True` default (correct). A skill can pass the full 6-stage audit with confidence=0.95, verdict=pass, necessary=True and still stay as draft if the default is wrong. Per SkillsBench (arxiv:2602.12670), an audit that cannot promote produces the same result as no audit — zero measurable benefit.

4. **Agent tool add (`tool_implementations.py:~241`)**: `manage_skills add` without explicit status auto-publishes via a `True` pref default, bypassing the audit entirely.

**Pre-existing gap:** Teacher prompt templates suggest `"confidence": 0.8`; injection floor is `0.85`. Teacher drafts with LLM-generated confidence ≤ 0.84 never inject even when everything else is correct.

### Fix

**Architectural principle:** Extraction always produces drafts. `auto_approve_skills` controls two things and only two things: (1) whether a passing audit auto-promotes to published; (2) which drafts appear in injection context. It has no role at extraction time.

**Change 1 — `skill_extractor.py`:** Remove the pref check entirely. Always `status="draft"`. Add a comment explaining that the audit pipeline (`_audit_one_skill`) handles promotion.

**Change 2 — `agent_loop.py`:** Replace the `min_conf=2.0` hack with a source-aware pre-filter:
```python
_all_skills = sm.load(owner=owner)
if not _prefs.get("auto_approve_skills", True):
    _all_skills = [
        s for s in _all_skills
        if s.get("status") == "published"
        or (s.get("status") == "draft"
            and s.get("source") == "teacher-escalation")
    ]
```
When `auto_approve=False`, published skills and teacher-escalation drafts both inject. The teacher→student fast path is preserved even in manual-review mode. When `True` (default), all skills pass to `get_relevant_skills()` at the normal confidence floor. `sm.load()` is called exactly once.

**Change 3 — `skills_routes.py`:** Default `True` confirmed; add docstring to `_audit_auto_publish_policy()` explaining why: the audit is the quality gate; users who want manual review can toggle the setting off in Brain > Skills.

**Change 4 — `tool_implementations.py`:** Remove pref check from `manage_skills add` fallback. Always `"draft"`. Explicit `status` from caller still wins (guarded by `if not _status_arg:`).

**Change 5 — `teacher_escalation.py`:** Change confidence suggestion `0.8` → `0.9` in both prompt templates (~195, ~293). The teacher is a SOTA model; 0.9 is accurate and reliably clears the 0.85 injection floor.

**Change 6 — `skills.py:~657`:** Update design comment to accurately describe both injection modes (auto_approve=True and False).

### Impact

- Pre-existing high-confidence drafts (confidence ≥ 0.85) will begin injecting after this fix when `auto_approve_skills=True` (the new default behavior). This is the correct behavior — they were previously blocked by the incorrect default. Users who want to review before injection can set `auto_approve_skills=False` in Brain > Skills.
- Teacher-escalation skills will reliably inject on the next turn after a failed task (as designed). Previously they were blocked entirely.
- The audit pipeline now functions as designed: skills that pass are promoted; the 6-stage audit produces measurable benefit.

## Files Changed

| File | Change |
|------|--------|
| `services/memory/skill_extractor.py` | Remove pref check; always draft |
| `src/agent_loop.py` | Source-aware pre-filter replacing min_conf=2.0 hack |
| `routes/skills_routes.py` | Confirm True default; add docstring |
| `src/tool_implementations.py` | Remove pref check; always draft fallback |
| `src/teacher_escalation.py` | Confidence 0.8→0.9 (two locations) |
| `services/memory/skills.py` | Update design comment |
| `tests/test_skill_lifecycle_correctness.py` | 11 new tests (NEW FILE) |

## Tests

11 tests in `tests/test_skill_lifecycle_correctness.py`:

**Source-text assertions (4):**
1. `auto_approve_skills` pref check NOT in `skill_extractor.py` (extraction decoupled)
2. `agent_loop.py` injection path default is `True`
3. `skills_routes.py` audit path default is `True`
4. `tool_implementations.py` no auto-approve-True pattern in manage_skills add fallback

**Behavioral assertions (7):**
5. Extraction with `auto_approve_skills=True` pref → status is `"draft"`
6. Extraction with `auto_approve_skills=False` pref → status is `"draft"` (always draft)
7. Extraction with no prefs → status is `"draft"`
8. Pre-filter with `auto_approve=True` → all 3 skills pass through
9. Pre-filter with `auto_approve=False` → learned draft excluded
10. Pre-filter with `auto_approve=False` → teacher-escalation draft included
11. Pre-filter with `auto_approve=False` → published skill always included

## Target Branch

- [x] This PR targets **`dev`**, not `main`.

## Linked Issue

Fixes # <!-- [add upstream issue number before filing] -->

## Type of Change

- [x] Bug fix
- [ ] New feature
- [ ] Refactor / cleanup (behaviour unchanged)
- [ ] Documentation only
- [ ] CI / tooling / configuration

## Checklist

- [x] I searched [open issues](https://github.com/pewdiepie-archdaemon/odysseus/issues) and [open PRs](https://github.com/pewdiepie-archdaemon/odysseus/pulls); this is not a duplicate. Related: #2750 (prompt token bloat).
- [x] This PR targets `dev`.
- [x] My changes are limited to the scope described above.
- [ ] **I am not an LLM agent submitting a bulk PR.** I reviewed and tested this change personally before submitting.

## How to Test

1. Trigger a complex agent task (≥ 2 rounds, ≥ 3 tool calls). Confirm new skill appears in Brain > Skills as **draft**, not published.
2. Click "Audit" on the draft. Confirm status changes to **published** after passing. (The audit runs and its verdict now takes effect.)
3. In a new conversation on the same topic, confirm the published skill appears in the agent's context.
4. Configure a teacher model (Settings > Brain). Trigger a task the student model fails. Confirm a 🎓 teacher-written draft appears. Start a new conversation on the same topic — confirm the teacher draft IS in the agent context (confidence 0.9 ≥ floor 0.85).
5. Turn off "Auto-approve skills" in Brain > Skills. Trigger a new extraction. Confirm the new draft does NOT inject into agent context (unless it's source=teacher-escalation).
6. With auto_approve off: trigger teacher escalation. Confirm the teacher draft still injects (the source-aware pre-filter allows it).
7. Ask the agent to call `manage_skills add` with no explicit status. Confirm the new skill appears as **draft** in Brain > Skills.
8. Run `pytest tests/test_skill_lifecycle_correctness.py -v` — 11 tests pass.
9. Run `pytest tests/ -q` — full suite passes (minus pre-existing failures).

---

## Filing Notes

- 1 commit on branch `fix/skill-lifecycle-correctness`:
  - `126e1b62` — all 5 production file changes + 11 new tests
- Branch built from `upstream-mirror` — clean, no fork-specific history.
- **File upstream issue first**, then add the upstream issue number to `Fixes #` above.
- ROADMAP context: "Agent prompt/context bloat" (removes spurious published skills that forced pre-task skill lookups) and "Skill/tool prompt-injection audit" (reduces unconditional trust paths in the skill pipeline).
- Research citations for PR description: arxiv:2602.12670 (SkillsBench — audit must promote to provide benefit), arxiv:2504.07079 (SkillWeaver — teacher→student transfer requires immediate injection).

## Visual / UI Changes

None. The skill draft/publish distinction is already visible in Brain > Skills. The only observable UI change is that:
- Auto-extracted skills always appear as drafts (not published) until the audit promotes them
- Previously blocked teacher-escalation drafts now appear in matched-skills context blocks
