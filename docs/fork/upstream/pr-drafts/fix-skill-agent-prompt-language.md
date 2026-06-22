# PR Draft: fix/skill-agent-prompt-language → pewdiepie-archdaemon/odysseus:dev

**Branch:** `jdmanring/odysseus:fix/skill-agent-prompt-language`
**Issue:** [#85](https://github.com/jdmanring/odysseus/issues/85)
**Base:** `upstream-mirror` (latest upstream commit)
**Status:** Ready to file

---

## Title

`fix(agent): reframe skill prompts as advisory — remove mandatory consultation and unconditional authority language`

---

## Summary

### Problem

Three strings in `src/agent_loop.py` instruct the agent to consult the skill registry before every task and to treat auto-extracted skills as proven, authoritative procedures. This creates a mandatory pre-task consultation loop: the agent calls `manage_skills list` → `manage_skills view` before starting most tasks, consuming agent rounds on overhead rather than the user's request.

**`manage_skills` tool description (line ~417):**
> "Use this **BEFORE doing domain work** — there may already be a procedure (published or draft) that prescribes the correct steps. Drafts written by the teacher loop are **authoritative guidance** even though they're not yet published."

**Matched-skills injection header (lines ~1274–1279):**
> "Each is a **procedure proven to work**. **Follow them step by step.**"

**Skill index block header (lines ~1447–1453):**
> "Procedures the assistant should **consult before doing domain work**. [...] **treat them as authoritative guidance**"

Skills are LLM extractions from a 12-message context window — they are approximations, not verified procedures. "Proven to work" and "authoritative guidance" overstate their reliability. "BEFORE doing domain work" makes consultation mandatory rather than conditional.

### Impact

On sessions with a populated skill index, the agent spends 2–4 rounds consulting the skill registry before answering. This is directly visible as "stuck looking at tools instead of doing work" — the agent is following the instructions exactly. For small-context local models (4k/8k), this overhead crowds the user's actual request out of context.

ROADMAP identifies "Agent prompt/context bloat" and "Skill/tool prompt-injection audit" as high-priority items. This fix addresses a direct cause of both: mandatory manage_skills calls inflate per-request token usage, and the "authoritative guidance" framing is a prompt-injection amplifier (a malicious skill name or description is more likely to be followed if the agent is told skills are authoritative).

### Fix

Three targeted string replacements in `src/agent_loop.py`:

**Change 1 — `manage_skills` tool description:**

Remove "BEFORE doing domain work" mandate and "authoritative guidance" label. Replace with a conditional check: check the registry when the domain looks like it may have prior work; frame drafts as candidates from prior sessions.

**Change 2 — matched-skills injection header:**

Remove "proven to work" and "Follow them step by step". Replace with "candidate procedures — evaluate fit before applying; use own judgment if the match is weak."

**Change 3 — skill index block header:**

Remove "consult before doing domain work" mandate and "treat them as authoritative guidance". Replace with "reference procedures for this session — when a task closely matches, apply; evaluate drafts before following."

## Files changed

- `src/agent_loop.py` — 3 string literal changes (tool description, matched-skills header, skill index header)
- `tests/test_agent_skill_prompt_language.py` — 6 new tests (NEW FILE)

## Tests

12 static source-text assertions in `tests/test_agent_skill_prompt_language.py`
(6 absence checks + 6 presence checks for replacement language):

**Absence — bad strings removed:**
1. `"BEFORE doing domain work"` not in `agent_loop.py`
2. `"authoritative guidance"` not in `manage_skills` tool description block
3. `"proven to work"` not in `agent_loop.py`
4. `"Follow them step by step"` not in `agent_loop.py`
5. `"consult before doing domain work"` not in `agent_loop.py`
6. `"treat them as authoritative"` not in `agent_loop.py`

**Presence — advisory replacement language in place:**
7. `"check the skill registry — there may be a reusable procedure"` in `agent_loop.py`
8. `"Published skills are user-reviewed; drafts are candidate procedures from prior sessions"` in `agent_loop.py`
9. `"candidate procedures"` in matched-skills injection header
10. `"use your own judgment"` in matched-skills injection header
11. `"Reference procedures for this session"` in skill index header
12. `"evaluate fit before following"` in skill index header

## Target branch

- [x] This PR targets **`dev`**, not `main`.

## Linked Issue

Fixes # <!-- [add upstream issue number before filing] -->
Relates to #2750 (Agent prompt token bloat: measure, slim, and modularize)

## Type of Change

- [x] Bug fix
- [ ] New feature
- [ ] Refactor / cleanup (behaviour unchanged)
- [ ] Documentation only
- [ ] CI / tooling / configuration

## Checklist

- [x] I searched [open issues](https://github.com/pewdiepie-archdaemon/odysseus/issues) and [open PRs](https://github.com/pewdiepie-archdaemon/odysseus/pulls); this is not a duplicate. Relates to #2750 (prompt bloat parent) and ROADMAP "Skill/tool prompt-injection audit".
- [x] This PR targets `dev`
- [x] My changes are limited to the scope described above; no unrelated refactors or whitespace changes mixed in.
- [ ] **I am not an LLM agent submitting a bulk PR.** I reviewed and tested this change personally before submitting.

## How to Test

1. Start Odysseus with at least one published skill in Brain > Skills.
2. Send a simple request (e.g. "what is 2+2"). The agent should answer directly without calling `manage_skills list` first.
3. Send a request clearly in a skill's domain. The agent may consult the skill registry, but should not do so for every request.
4. Run `pytest tests/test_agent_skill_prompt_language.py -v` — 12 tests pass (6 absence + 6 presence).
5. Run `pytest tests/ -q` — full suite passes (minus pre-existing failures in `test_model_context`, `test_tool_parsing_pycall`, `test_workspace_*`).

---

## Filing Notes

- 2 commits on branch `fix/skill-agent-prompt-language`:
  - `383fbc6f` — 3 string literal replacements in `agent_loop.py`
  - `960ec5db` — strengthened tests (added 6 presence assertions, fixed manage_skills index anchoring)
- Branch built from `upstream-mirror` — clean, no fork-specific history.
- **File upstream issue first**, then add upstream issue number to `Fixes #` above.
- Reference upstream #2750 when filing — this PR reduces one measurable component of per-request prompt overhead (mandatory manage_skills rounds).
- ROADMAP context: addresses both "Agent prompt/context bloat" (removes mandatory pre-task tool calls) and "Skill/tool prompt-injection audit" (reduces unconditional trust in user-editable skill content).

## Visual / UI changes

None. The change is to agent reasoning instructions — no UI elements are modified.
