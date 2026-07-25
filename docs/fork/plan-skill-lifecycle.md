# Plan: Skill Lifecycle Correctness + World-Class Cultivation Pipeline

**Status:** Approved: implementation in progress
**Branches:** `fix/skill-lifecycle-correctness` (#86), `feat/skill-quality-signals` (#87)
**Research reference:** `docs/dev/skill-system-architecture.md`

---

## Problem Statement

The Brain -> Skills pipeline has four correctness bugs that together break the autonomous
cultivation loop: skills are either never promoted (audit can't publish) or injected
without proper quality gating (teacher drafts blocked, agent-added skills auto-published).
Beyond correctness, the retrieval layer uses Jaccard similarity which systematically
under-retrieves skills with distinctive procedural vocabulary.

---

## Phase 1: Correctness Fix

**Branch:** `fix/skill-lifecycle-correctness`
**Origin:** `upstream-mirror`
**Issue:** `jdmanring/odysseus` #86

### Bug 1: `skill_extractor.py`: extraction has unnecessary pref dependency

`skill_extractor.py:274` checks `auto_approve_skills` to decide draft vs published
status at extraction time. This is semantically wrong. Extraction should always produce
draft skills: the audit pipeline, not the extractor, is the quality gate.

**Fix:** Remove the `auto_approve_skills` pref check entirely. Always set
`_initial_status = "draft"`. Remove the `_load_prefs` import and `_prefs` variable
if only used in this block.

### Bug 2: `agent_loop.py:1242`: injection gate blocks all drafts including teacher-escalation

`agent_loop.py:1242` defaults `auto_approve_skills` to `False`, which causes
`_skill_min_conf = 2.0` always. No draft can have confidence >= 2.0. Teacher-escalation
drafts with confidence=0.9 are blocked. The SkillWeaver teacher->student transfer pattern
(arxiv:2504.07079) requires teacher drafts to inject immediately, this is broken.

**Fix:** Restore default to `True`. Replace the `min_conf=2.0` hack with a source-aware
pre-filter that is applied to the full skill list before `get_relevant_skills()`:

```python
_all_skills = sm.load(owner=owner)
if not _prefs.get("auto_approve_skills", True):
    _all_skills = [
        s for s in _all_skills
        if s.get("status") == "published"
        or (s.get("status") == "draft"
            and s.get("source") == "teacher-escalation")
    ]
try:
    _skill_min_conf = float(_prefs.get(
        "skill_min_confidence",
        get_setting("skill_autosave_min_confidence", 0.85)))
except (TypeError, ValueError):
    _skill_min_conf = 0.85
```

Pass `skills=_all_skills` (not `skills=sm.load(owner=owner)`) to `get_relevant_skills()`.
Do not call `sm.load()` twice (SD-7).

### Bug 3: `skills_routes.py:504`: audit can never promote skills

`skills_routes.py:504` defaults `auto_approve_skills` to `False`. The
`_audit_finalize_status()` function receives `auto_publish=False` and never publishes
even on verdict=pass, confidence=0.95. Per SkillsBench (arxiv:2602.12670), an audit
that cannot promote produces zero benefit.

**Fix:** Restore default to `True`:
```python
enabled = bool(prefs.get("auto_approve_skills", True))
```

### Bug 4: `tool_implementations.py:241`: agent-added skills auto-publish (missed in prior session)

`tool_implementations.py:241` defaults `auto_approve_skills` to `True`, causing
agent-added skills via `manage_skills add` to auto-publish without going through the
audit pipeline. This is the opposite of the extractor (fixed) and inconsistent.

**Fix:** Change the fallback inside `if not _status_arg:` to always use draft:
```python
_status_arg = "draft"
```
Remove pref loading lines if only used in this block. Explicit `status` from the caller
always wins (check for `if not _status_arg:` guard: SD-6).

### Pre-existing gap: `teacher_escalation.py`: confidence 0.8 < injection floor 0.85

The teacher prompt template at lines ~195 and ~293 suggests `"confidence": 0.8`. The
injection floor is 0.85. Teacher drafts with LLM-generated confidence <= 0.84 fail the
injection gate even with the default fixed to `True`. This silently breaks the
teacher->student transfer path for any teacher-generated skill at the suggested confidence.

**Fix:** Change both occurrences from `"confidence": 0.8,` to `"confidence": 0.9,`.
The teacher model is a SOTA model, 0.9 is appropriate and ensures reliable injection.

Verify both locations first: `grep -n '"confidence": 0' src/teacher_escalation.py`

### Documentation update: `skills.py:657-662`

The comment at lines 657-662 says teacher drafts inject "without a manual publish click."
After Phase 1, this is conditionally true: true when `auto_approve_skills=True` (default);
false when `False` (manual-review mode, teacher drafts wait for user publish or audit
promotion). Update the comment to reflect both modes.

---

## Phase 1 Implementation Steps

Execute in order. Read each file section before editing (CLAUDE.md: "read before coding").

1. Create fork issue #86: `fix(skills): auto_approve_skills semantics broken; extraction always draft, audit defaults to trust`

2. Create branch: `git checkout upstream-mirror && git checkout -b fix/skill-lifecycle-correctness`

3. `services/memory/skill_extractor.py` (~264-277): Remove pref check block; always draft. Verify import removal does not break other code in the function.

4. `src/agent_loop.py` (~1236-1264): Restore default `True`; implement source-aware pre-filter; store `sm.load()` result in `_all_skills`; pass it to `get_relevant_skills()`.

5. `routes/skills_routes.py` (~504): Change default to `True`.

6. `src/tool_implementations.py` (~237-243): Change fallback to `_status_arg = "draft"`; remove pref loading if unused.

7. `src/teacher_escalation.py` (~195, ~293): Change both `0.8` -> `0.9`.

8. `services/memory/skills.py` (~657-662): Update comment.

9. `tests/test_skill_extraction_gate.py`: Update 3 tests per SD-1:
   - `test_injection_path_auto_approve_default_is_false` -> rename `_true`, assert `True`
   - `test_audit_finalization_auto_approve_default_is_false` -> rename `_true`, assert `True`
   - `test_auto_approve_default_is_draft` -> rewrite: extraction is always draft regardless of pref

10. Write `tests/test_skill_lifecycle_correctness.py` (10 tests, see test spec below).

11. Run tests: `pytest tests/test_skill_lifecycle_correctness.py tests/test_skill_extraction_gate.py -v` then `pytest tests/ -q`.

12. Commit (see commit message spec below).

13. Cherry-pick to `develop`. Expect conflicts on 4 files from prior session's incorrect commits; resolve all in favor of the incoming changes (SD-2). The branch is authoritative.

14. Write `docs/fork/upstream/issue-drafts/fix-skill-lifecycle-correctness.md` and `docs/fork/upstream/pr-drafts/fix-skill-lifecycle-correctness.md`.

15. Update `docs/fork/active-work.md` with issue #86 entry.

---

## Phase 1 Test Spec: `tests/test_skill_lifecycle_correctness.py`

10 tests verifying the fixed semantics:

**Source-text assertions (4):**
1. `auto_approve_skills` pref check is NOT present in `skill_extractor.py` (extraction decoupled)
2. `agent_loop.py` injection path default is `True` (assert `'auto_approve_skills", True)'`)
3. `skills_routes.py` audit path default is `True`
4. `tool_implementations.py` does NOT have `auto_approve_skills", True)` in the `manage_skills add` path

**Behavioral assertions (6):**
5. Extraction with `auto_approve_skills=True` pref -> status is `"draft"`
6. Extraction with `auto_approve_skills=False` pref -> status is `"draft"` (always draft)
7. `manage_skills add` with no explicit status -> status is `"draft"`
8. `get_relevant_skills()` with `auto_approve=False` pre-filter: teacher-escalation draft IS included
9. `get_relevant_skills()` with `auto_approve=False` pre-filter: `source=learned` draft is NOT included
10. `get_relevant_skills()` with `auto_approve=True` pre-filter: `source=learned` draft IS included

Use `_FakeSession` / `_FakeSkillsManager` pattern from `test_skill_extraction_gate.py`.
For injection tests (8-10): test the pre-filter logic by calling it with known skill lists
and asserting on the result contents; do not require a full agent_loop invocation.

---

## Phase 1 Commit Message

```
fix(skills): correct auto_approve_skills semantics across skill pipeline

Extraction always produces draft skills; auto_approve_skills controls
whether the audit promotes passing skills (default: True) and which
drafts are injected (default: True, published + all at confidence floor;
False, published + teacher-escalation drafts only via source-aware filter).

Four bugs fixed:
  1. skill_extractor.py: remove auto_approve_skills check; extraction is
     always draft; audit pipeline handles promotion.
  2. agent_loop.py: restore default True; replace min_conf=2.0 hack with
     source-aware pre-filter that preserves teacher-escalation injection.
  3. skills_routes.py: restore default True; audit that passes must
     promote; informational-only audit produces zero benefit (SkillsBench
     2025, arxiv:2602.12670).
  4. tool_implementations.py: manage_skills add always produces draft;
     agent-added skills go through the same audit pipeline.

Also: increase teacher confidence suggestion 0.8→0.9 (both locations in
teacher_escalation.py) so teacher-written drafts reliably clear the 0.85
injection floor (SkillWeaver strong→weak transfer, arxiv:2504.07079).

Tests: 10 new in test_skill_lifecycle_correctness.py; 3 updated in
test_skill_extraction_gate.py to match corrected defaults.
```

---

## Phase 2: World-Class Quality Signals

**Branch:** `feat/skill-quality-signals`
**Origin:** `upstream-mirror`
**Issue:** `jdmanring/odysseus` #87: `feat(skills): BM25 retrieval scoring + composite skill health score`

### 2A: BM25 Hybrid Retrieval (`services/memory/skills.py`)

Replace pure Jaccard in `get_relevant_skills()` with hybrid `0.5 x Jaccard + 0.5 x BM25_norm`.

Add two module-level helpers near `_jaccard` and `_tokenize`:

```python
from math import log as _log

def _compute_idf(skills):
    N = max(len(skills), 1)
    df = {}
    for sk in skills:
        tokens = set(_tokenize(" ".join([
            sk.get("name", ""), sk.get("description", ""),
            sk.get("when_to_use", ""),
            " ".join(sk.get("tags", []) or []),
        ])))
        for t in tokens:
            df[t] = df.get(t, 0) + 1
    return {t: _log((N - n + 0.5) / (n + 0.5) + 1.0) for t, n in df.items()}

def _bm25_score(query_tokens, skill_tokens_list, idf, k1=1.5, b=0.75, avg_len=60.0):
    tf_map = {}
    for t in skill_tokens_list:
        tf_map[t] = tf_map.get(t, 0) + 1
    doc_len = len(skill_tokens_list)
    score = 0.0
    for qt in query_tokens:
        if qt not in idf:
            continue
        tf = tf_map.get(qt, 0)
        score += idf[qt] * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * doc_len / avg_len))
    return score
```

Normalize: `bm25_norm = bm25_raw / (bm25_raw + 3.0)` (sigmoid-like; approaches 1.0
for very high BM25 scores; 3.0 tuning constant calibrated to Odysseus skill length).

IDF caching on `SkillsManager`:
- Add `self._idf_cache = None` in `__init__`
- Call `self._idf_cache = None` in `add_skill()`, `update_skill()`, `delete_skill()`
- Compute lazily: `if self._idf_cache is None: self._idf_cache = _compute_idf(all_skills)`

### 2B: Composite Health Score (`services/memory/skills.py`)

Add `_health_score(skill)` function returning 0-100 integer from existing sidecar fields.
Calibrated to SkillOps five diagnostic dimensions (arxiv:2605.13716):

```python
def _health_score(skill):
    score = 0
    score += int(skill.get("confidence", 0.5) * 40)  # 0–40 pts
    score += {"pass": 30, "inconclusive": 15, "needs_work": 10,
              "fail": 0, "skipped": 5}.get(skill.get("audit_verdict"), 15)  # 0–30 pts
    uses = min(skill.get("uses", 0), 20)
    score += int((uses / 20) * 20)  # 0–20 pts (log-scaled)
    necessity = skill.get("necessity") or {}
    if necessity.get("necessary") is not False:
        score += 10  # 0 or +10 pts
    return min(score, 100)
```

Add `"health_score": _health_score(result)` to `Skill.to_dict()` return dict.

### 2C: UI Badge (`static/js/skills.js`)

Find confidence % rendering location on skill card. Add color-coded health badge
(green >= 80, yellow 60-79, red < 60) with "Health: N/100" tooltip.

### Phase 2 Test Spec: `tests/test_skill_retrieval_bm25.py` (6 tests)

1. BM25 ranks distinctive-vocabulary skill above generic for specific query
2. BM25 returns 0.0 for query with no corpus overlap
3. Hybrid `get_relevant_skills()` with empty skills list -> empty list, no exception
4. `_health_score` returns 100 for ideal skill (pass, 0.95 conf, 20 uses, necessary)
5. `_health_score` returns < 30 for failed/unused/unnecessary skill
6. `_health_score` handles None/missing fields without raising

### Phase 2 Commit Message

```
feat(skills): BM25 hybrid retrieval and composite skill health score

Retrieval: replace pure Jaccard with 0.5 Jaccard + 0.5 BM25 hybrid.
BM25 weights distinctive tokens (tool names, domain terms) over common
terms, improving skill matching for queries with rare vocabulary.
IDF cached on SkillsManager, invalidated on library mutations.
(SkillRet 2025, arxiv:2605.05726; Skill Retrieval Benchmark arxiv:2604.24594)

Health score: new health_score field (0-100) in Skill.to_dict() from
existing sidecar signals: confidence (40 pts), audit_verdict (30 pts),
uses (20 pts), necessity (10 pts). Color-coded badge on Brain > Skills
cards. No new data stored; derived from existing fields.
(SkillOps 2025, arxiv:2605.13716)

Tests: 6 new in test_skill_retrieval_bm25.py.
```

---

## Senior Developer Audit Notes

| ID | Issue | Resolution |
|----|-------|-----------|
| SD-1 | 3 tests in `test_skill_extraction_gate.py` will fail after Phase 1 | Update them in Step 9 |
| SD-2 | Cherry-pick to develop will conflict (prior session's incorrect commits) | Resolve all conflicts in favor of incoming branch |
| SD-3 | Pre-existing high-confidence drafts will begin injecting after fix | Note in PR description; user can opt out with `auto_approve_skills=False` |
| SD-4 | BM25 IDF is O(N) per call | Cache on SkillsManager instance, invalidate on mutations |
| SD-5 | Teacher confidence 0.8 appears in two locations | Grep to verify both before editing |
| SD-6 | `manage_skills add` with explicit status must not be overridden | Fix is inside `if not _status_arg:` guard: explicit arg still wins |
| SD-7 | Injection path must not call `sm.load()` twice | Store result in `_all_skills`, filter it, pass to `get_relevant_skills()` |
| SD-8 | `skills.py:657-662` comment will become inaccurate | Update in Step 8 to describe both modes |
| SD-9 | `health_score` in `to_dict()` has negligible cost | No caching needed |
| SD-10 | Phase 2 JS changes must use correct field name | Trace rendering path in `skills.js` before editing |

---

## Behavioral Verification (Phase 1)

After implementing and cherry-picking to develop:

1. Complex task (>= 2 rounds, >= 3 tools) -> skill appears in Brain > Skills as **draft**
2. Trigger audit on draft -> skill status changes to **published** (audit promotes)
3. Next agent conversation on same domain -> published skill appears in agent context
4. Configure teacher model; trigger a failing task -> 🎓 draft appears; next conversation on same topic -> teacher draft IS in agent context
5. Turn OFF "Auto-approve skills" toggle -> extract new skill -> stays draft after audit
6. With toggle OFF: trigger teacher escalation -> teacher draft IS still in agent context (pre-filter allows it)
7. Agent `manage_skills add` without status -> appears in Brain > Skills as **draft**
8. `pytest tests/test_skill_lifecycle_correctness.py tests/test_skill_extraction_gate.py -v`, all pass

---

## Branch Structure

| Branch | Issue | Origin | Status |
|--------|-------|--------|--------|
| `fix/skill-extraction-threshold` | #84 | upstream-mirror | Complete; PR draft staged |
| `fix/skill-agent-prompt-language` | #85 | upstream-mirror | Complete; PR draft staged |
| `fix/skill-lifecycle-correctness` | #86 | upstream-mirror | **In progress** |
| `feat/skill-quality-signals` | #87 | upstream-mirror | Planned |

---

## Documents Created by This Plan

| File | Type | Status |
|------|------|--------|
| `docs/dev/skill-system-architecture.md` | upstream-candidate | Created |
| `docs/fork/plan-skill-lifecycle.md` (this file) | fork-only | Created |
| `docs/fork/upstream/issue-drafts/fix-skill-lifecycle-correctness.md` | fork-only | Pending |
| `docs/fork/upstream/pr-drafts/fix-skill-lifecycle-correctness.md` | fork-only | Pending |
| `docs/fork/upstream/issue-drafts/feat-skill-quality-signals.md` | fork-only | Pending |
| `docs/fork/upstream/pr-drafts/feat-skill-quality-signals.md` | fork-only | Pending |
