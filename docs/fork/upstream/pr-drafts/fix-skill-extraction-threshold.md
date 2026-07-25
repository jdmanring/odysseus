# PR Draft: fix/skill-extraction-threshold -> odysseus-dev/odysseus:dev

**Branch:** `fix/skill-extraction-threshold`
**Issue:** [#84](https://github.com/jdmanring/odysseus/issues/84)
**Base:** `upstream-mirror` (latest upstream commit)
**Status:** Ready to file

---

## Title

`fix(skills): raise extraction threshold, align confidence floor, default auto-approve to draft`

---

## Summary

### Problem

The skill auto-extraction system has four defects that combine to pollute `data/skills/`
with low-quality, unreviewed skills and inject them into the agent's context without user
review:

**1. OR-based extraction gate is too permissive**

`routes/chat_helpers.py` triggers extraction when `agent_rounds >= 2 OR agent_tool_calls >= 2`.
Any session that reads and writes a single file qualifies (1 round, 2 tool calls). The gate
in `skill_extractor.py` uses the same OR logic. Skills are therefore extracted from routine
housekeeping tasks that contain no reusable procedure.

**2. `MIN_CONFIDENCE = 0.6` creates zombie skills**

The extractor saves skills with confidence >= 0.6, but the injection gate in `agent_loop.py`
uses a default floor of 0.85. Skills in the 0.60-0.84 range are written to `data/skills/`
but never injected into the agent; they accumulate as dead weight without contributing to
agent capability.

**3. `auto_approve_skills` defaults to `True` in the extractor**

Extracted skills are auto-published before the user reviews them. A skill extracted from a
failed or non-representative session becomes active agent context immediately.

**4. `auto_approve_skills` defaults to `True` in the injection and audit paths**

`agent_loop.py` line 1231 and `skills_routes.py` `_audit_auto_publish_policy` also default
`auto_approve_skills` to `True`. Even with the extractor saving drafts, these paths allow
draft skills at >= 0.85 confidence to be injected into the agent's prompt without the user
publishing them. The defect at the injection callsite is:

```python
if not _prefs.get("auto_approve_skills", True):   # ← True allows drafts through by default
    _skill_min_conf = 2.0  # published-only
```

Setting `min_conf = 2.0` blocks drafts only when `auto_approve_skills=False`. With the default
`True`, drafts at >= 0.85 pass the gate without the user ever opening Brain > Skills.

### Fix

**`services/memory/skill_extractor.py`:**
- `MIN_CONFIDENCE`: `0.6` -> `0.85`, aligning with the injection floor; stop saving skills the agent will never see
- Extraction gate: `if round_count < 2 and tool_count < 2` -> `if round_count < 2 or tool_count < 3` (require rounds >= 2 **and** tools >= 3; filters out trivial two-call sessions)
- `auto_approve_skills` pref default: `True` -> `False`: skills land as drafts; user publishes from Brain > Skills

**`routes/chat_helpers.py`:**
- Outer gate: `(agent_rounds >= 2 or agent_tool_calls >= 2)` -> `(agent_rounds >= 2 and agent_tool_calls >= 3)` to match the new AND logic

**`src/agent_loop.py`:**
- Injection path default: `auto_approve_skills", True` -> `auto_approve_skills", False`; only
  published (user-reviewed) skills are injected by default; drafts require explicit opt-in
- Updated inline comment to reflect the new default

**`routes/skills_routes.py`:**
- `_audit_auto_publish_policy`: `auto_approve_skills", True` -> `auto_approve_skills", False`:
  skills that pass the autonomous skill audit remain as drafts until the user publishes them

## Files changed

- `services/memory/skill_extractor.py`: `MIN_CONFIDENCE`, gate condition, `auto_approve_skills` default
- `routes/chat_helpers.py`: outer extraction gate condition
- `src/agent_loop.py`: injection path `auto_approve_skills` default + comment
- `routes/skills_routes.py`: audit-finalization `auto_approve_skills` default
- `tests/test_skill_extraction_gate.py`: 5 source-text tests (NEW FILE)

## Tests

5 source-text assertions in `tests/test_skill_extraction_gate.py`, verifying the
constants and defaults the change introduces:

1. `MIN_CONFIDENCE = 0.85` is present in `skill_extractor.py`.
2. `round_count < 2 or tool_count < 3` (the AND gate) is present in `skill_extractor.py`.
3. `agent_rounds >= 2 and agent_tool_calls >= 3` (the AND gate) is present in `chat_helpers.py`.
4. `auto_approve_skills", False` is present in `agent_loop.py` (injection path).
5. `auto_approve_skills", False` is present in `skills_routes.py` (audit path).

Runtime behaviour (the gate skipping below-threshold sessions, the confidence floor, and
draft-not-published status) is exercised by the manual steps under "How to Test".

## Target branch

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

- [x] I searched [open issues](https://github.com/odysseus-dev/odysseus/issues) and [open PRs](https://github.com/odysseus-dev/odysseus/pulls); this is not a duplicate. Related: PR #4520 (junk name rejection, a different problem), issue #4466 (skill tier curation, future work).
- [x] This PR targets `dev`
- [x] My changes are limited to the scope described above; no unrelated refactors or whitespace changes mixed in.
- [ ] **I am not an LLM agent submitting a bulk PR.** I reviewed and tested this change personally before submitting.

## How to Test

1. Run an agent task with exactly 2 rounds and 2 tool calls (e.g. list todos + add one); confirm no skill extraction fires in the log.
2. Run an agent task with 2 rounds and 3+ tool calls, and confirm `[skill-extract]` log entry appears and skill is saved as `"draft"` (not `"published"`) in Brain > Skills.
3. Open Brain > Skills and confirm no draft appears in the agent's injected context (send a simple request; agent should not call `manage_skills` to retrieve the draft).
4. Publish a draft manually; confirm the published skill IS injected on subsequent relevant requests.
5. Run `pytest tests/test_skill_extraction_gate.py -v` (5 tests pass).
6. Run `pytest tests/ -q`: full suite passes (minus pre-existing failures in `test_model_context`, `test_tool_parsing_pycall`, `test_workspace_*`).

---

## Filing Notes

- 2 commits on branch `fix/skill-extraction-threshold`:
  - `5b8c0364`: original threshold, gate, extractor auto-approve default
  - `1705c1e4`: injection and audit-finalization auto-approve defaults + strengthened tests
- Branch built from `upstream-mirror` (clean, no fork-specific history).
- **File upstream issue first**, then add the upstream issue number to `Fixes #` above.
- ROADMAP context: "Agent prompt/context bloat"; reduces both the volume of skills saved to disk
  and the number injected into the agent prompt per request.

## Visual / UI changes

None. The skill draft/publish distinction is already visible in Brain > Skills. The only
UI-observable change is that auto-extracted skills appear as drafts and are not injected
into the agent until the user publishes them.
