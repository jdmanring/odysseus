# Issue Draft: fix/skill-lifecycle-correctness → odysseus-dev/odysseus

**Fork issue:** [#86](https://github.com/jdmanring/odysseus/issues/86)
**Branch:** `jdmanring/odysseus:fix/skill-lifecycle-correctness`

---

## Title

`fix(skills): auto_approve_skills semantics broken — extraction always draft, audit defaults to trust`

---

## Body

### Problem

Four bugs in the `auto_approve_skills` preference handling break the autonomous skill cultivation pipeline. Together they prevent the audit from promoting skills, break teacher→student skill transfer, and allow agent-added skills to bypass the audit entirely.

**Bug 1 — `skill_extractor.py:~274`: extraction has unnecessary and incorrect pref dependency**

The extractor reads `auto_approve_skills` to decide draft vs published status. This is the wrong place for that check: extraction should always produce draft skills. The audit pipeline (`_audit_one_skill`) is the quality gate, not the extractor.

The upstream default (`True`) caused extraction to auto-publish immediately — before the audit had run. A skill extracted from a failed or non-representative session could become active agent context instantly with no quality testing.

**Bug 2 — `agent_loop.py:~1231`: injection gate blocks all drafts including teacher-escalation**

The injection block sets `_skill_min_conf = 2.0` when `auto_approve_skills=False`. No draft can have confidence ≥ 2.0, so all drafts are blocked — including teacher-escalation drafts with confidence=0.9.

The design comment at `skills.py:657–662` explicitly says teacher drafts should inject "without a manual publish click" so the student agent can retry a failed task on the next turn. This is the SkillWeaver strong→weak model skill transfer pattern (arxiv:2504.07079, +54.3% task success on WebArena). The `min_conf=2.0` hack silently breaks this.

**Bug 3 — `skills_routes.py:~504`: audit can never promote skills**

`_audit_auto_publish_policy()` defaulted `auto_approve_skills` to `True` in upstream — correct. The `_audit_finalize_status()` function receives `auto_publish=False` when the default is wrong, and will never publish even on verdict=pass, confidence=0.95.

Per SkillsBench (arxiv:2602.12670, 2025): self-generated skills without curation provide zero measurable benefit. An audit that cannot promote produces the same result as no audit. The 6-stage audit pipeline that costs multiple LLM calls becomes informational-only decoration.

**Bug 4 — `tool_implementations.py:~241`: `manage_skills add` auto-publishes by default**

The `manage_skills` tool handler uses `auto_approve_skills` with a `True` default for the fallback status. When an agent calls `manage_skills add` without specifying a status (the common case), the skill is published immediately — bypassing the audit pipeline entirely.

**Pre-existing gap — `teacher_escalation.py:~195,~293`: suggested confidence 0.8 < injection floor 0.85**

The teacher prompt template suggests `"confidence": 0.8` in both the new-skill and rewrite-skill prompt variants. The injection floor is `0.85`. Teacher-written drafts with LLM-generated confidence ≤ 0.84 fail the injection gate, silently breaking the teacher→student transfer path even when everything else is working correctly.

### Fix

1. **`skill_extractor.py`**: Remove the `auto_approve_skills` pref check entirely. Extraction always saves as draft. Add a comment explaining that the setting has no effect here — the audit handles promotion.

2. **`agent_loop.py`**: Replace the `min_conf=2.0` hack with a source-aware pre-filter applied to the full skill list before `get_relevant_skills()`:
   - `auto_approve=True` (default): all skills pass to retrieval at normal confidence floor
   - `auto_approve=False`: only published skills + `source=teacher-escalation` drafts pass
   This preserves the teacher→student fast path even in manual-review mode.

3. **`skills_routes.py`**: Confirm default `True` and document intent — the audit is the quality gate; users who want manual review before publishing can toggle the preference off.

4. **`tool_implementations.py`**: Remove the pref check from the `manage_skills add` fallback. Always default to draft. Explicit `status` from the caller still wins (the guard `if not _status_arg:` is preserved).

5. **`teacher_escalation.py`** (both locations ~195 and ~293): Change suggested confidence from `0.8` to `0.9`. The teacher is a SOTA model; 0.9 is accurate and reliably clears the 0.85 injection floor.

### Research Basis

- **SkillsBench** (arxiv:2602.12670, 2025): Curated skills raise pass rate +16.2 pp (33.9% → 50.1%). Self-generated skills with no curation provide zero benefit. The audit must be able to promote.
- **SkillWeaver** (arxiv:2504.07079, 2025): Strong→weak model skill transfer requires immediate availability (+54.3% task success on WebArena). Teacher-written drafts must inject on the next turn.

### Files Changed

- `services/memory/skill_extractor.py` — remove pref check; always draft
- `src/agent_loop.py` — source-aware pre-filter replacing min_conf=2.0 hack
- `routes/skills_routes.py` — confirm default True; document intent
- `src/tool_implementations.py` — manage_skills add always produces draft
- `src/teacher_escalation.py` — confidence suggestion 0.8→0.9 (two locations)
- `services/memory/skills.py` — update design comment at lines ~657–662
- `tests/test_skill_lifecycle_correctness.py` — 11 new tests (NEW FILE)

### Labels

`bug`, `skills`, `brain`

---

## Filing Notes

- File upstream issue first, then reference the issue number in the PR.
- Reference ROADMAP items: "Agent prompt/context bloat", "Skill/tool prompt-injection audit".
- Related upstream issue: #2750 (agent prompt token bloat — this reduces forced pre-task skill lookups by eliminating spurious published skills).
