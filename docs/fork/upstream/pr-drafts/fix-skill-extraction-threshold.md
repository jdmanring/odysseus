# PR Draft: fix/skill-extraction-threshold → pewdiepie-archdaemon/odysseus:dev

**Branch:** `jdmanring/odysseus:fix/skill-extraction-threshold`
**Issue:** [#84](https://github.com/jdmanring/odysseus/issues/84)
**Base:** `upstream-mirror` (latest upstream commit)
**Status:** Ready to file

---

## Title

`fix(skills): raise extraction threshold, align confidence floor, default auto-approve to draft`

---

## Summary

### Problem

The skill auto-extraction system has three defects that combine to pollute `data/skills/` with low-quality, unreviewed skills that increase prompt token usage on every subsequent agent request:

**1. OR-based extraction gate is too permissive**

`routes/chat_helpers.py` triggers extraction when `agent_rounds >= 2 OR agent_tool_calls >= 2`. Any session that reads and writes a single file qualifies (1 round, 2 tool calls). The gate in `skill_extractor.py` uses the same OR logic. Skills are therefore extracted from routine housekeeping tasks that contain no reusable procedure.

**2. `MIN_CONFIDENCE = 0.6` creates zombie skills**

The extractor saves skills with confidence ≥ 0.6, but the injection gate in `agent_loop.py` uses a default floor of 0.85. Skills in the 0.60–0.84 range are written to `data/skills/` but never injected into the agent — they accumulate as dead weight without contributing to agent capability.

**3. `auto_approve_skills` defaults to `True`**

Extracted skills are auto-published before the user reviews them. A skill extracted from a failed or non-representative session becomes active agent context immediately. The user has no default gate.

### Fix

**`services/memory/skill_extractor.py`:**
- `MIN_CONFIDENCE`: `0.6` → `0.85` — align with injection floor; stop saving skills the agent will never see
- Extraction gate: `if round_count < 2 and tool_count < 2` → `if round_count < 2 or tool_count < 3` — require rounds ≥ 2 **and** tools ≥ 3; filters out trivial two-call sessions
- `auto_approve_skills` pref default: `True` → `False` — skills land as drafts; user publishes from Brain > Skills

**`routes/chat_helpers.py`:**
- Outer gate: `(agent_rounds >= 2 or agent_tool_calls >= 2)` → `(agent_rounds >= 2 and agent_tool_calls >= 3)` — match the new AND logic

## Files changed

- `services/memory/skill_extractor.py` — `MIN_CONFIDENCE`, gate condition, `auto_approve_skills` default
- `routes/chat_helpers.py` — outer extraction gate condition
- `tests/test_skill_extraction_gate.py` — 5 new tests (NEW FILE)

## Tests

5 async unit tests in `tests/test_skill_extraction_gate.py` (pattern: `test_skill_extractor_stray_brace.py`):

1. `rounds=1, tools=2` → skipped (rounds below threshold)
2. `rounds=2, tools=2` → skipped (tools below new floor of 3)
3. `rounds=2, tools=3` → proceeds to LLM extraction call
4. `confidence=0.84` → dropped by `MIN_CONFIDENCE=0.85` floor
5. `auto_approve default=False` → skill status is `"draft"`, not `"published"`

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

- [x] I searched [open issues](https://github.com/pewdiepie-archdaemon/odysseus/issues) and [open PRs](https://github.com/pewdiepie-archdaemon/odysseus/pulls); this is not a duplicate. Related: PR #4520 (junk name rejection — different problem), issue #4466 (skill tier curation — future work).
- [x] This PR targets `dev`
- [x] My changes are limited to the scope described above; no unrelated refactors or whitespace changes mixed in.
- [ ] **I am not an LLM agent submitting a bulk PR.** I reviewed and tested this change personally before submitting.

## How to Test

1. Run an agent task with exactly 2 rounds and 2 tool calls (e.g. list todos + add one) — confirm no skill extraction fires in the log.
2. Run an agent task with 2 rounds and 3+ tool calls — confirm `[skill-extract]` log entry appears and skill is saved as `"draft"` (not `"published"`) in Brain > Skills.
3. Run `pytest tests/test_skill_extraction_gate.py -v` — 5 tests pass.
4. Run `pytest tests/ -q` — full suite passes.

---

## Filing Notes

- 1 commit: `5b8c0364` on branch `fix/skill-extraction-threshold`.
- Branch built from `upstream-mirror` — clean, no fork-specific history.
- **File upstream issue first**, then add the upstream issue number to `Fixes #` above.
- ROADMAP context: "Agent prompt/context bloat" — this fix reduces the volume of skills injected into agent context by raising the bar for what qualifies as extractable.

## Visual / UI changes

None. The skill draft/publish distinction is already visible in Brain > Skills. The only UI-observable change is that new auto-extracted skills appear as drafts rather than published.
