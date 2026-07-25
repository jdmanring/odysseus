# Upstream Issue Draft: fix-skill-agent-prompt-language

**File on:** `odysseus-dev/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/fix-skill-agent-prompt-language.md`
**Branch:** `fix/skill-agent-prompt-language`
**Type:** Bug
**Fork issue:** jdmanring/odysseus#85
**References upstream:** #2750 (Agent prompt token bloat)

---

## Title

`fix(agent): skill prompt instructions create mandatory consultation loop and unconditional authority`

---

## Body

**Install method:** Docker / manual Python

**OS / device:** Any

**Problem:**

Three strings in `src/agent_loop.py` instruct the agent to consult the skill registry *before every task* and to treat auto-extracted skills as proven, authoritative procedures. Together they produce a mandatory pre-task consultation loop that consumes agent rounds on overhead before any user work begins.

**String 1, `manage_skills` tool description (line ~417):**

> "Use this **BEFORE doing domain work** — there may already be a procedure (published or draft) that prescribes the correct steps. Drafts written by the teacher loop are **authoritative guidance** even though they're not yet published."

This instructs the agent to call `manage_skills list` before starting any task. For sessions with a populated skill index, the agent then calls `manage_skills view` for each seemingly relevant skill, consuming 2-3 rounds before real work begins.

**String 2, matched-skills injection header (lines ~1274-1279):**

> "Each is a **procedure proven to work**. **Follow them step by step.**"

Skills are LLM extractions from a 12-message context window. They are approximations, not verified procedures. "Proven to work" is factually incorrect. "Follow them step by step" causes unconditional execution even when the skill mismatches the current task.

**String 3, skill index block header (lines ~1447-1453):**

> "Procedures the assistant should **consult before doing domain work**. [...] **treat them as authoritative guidance**"

Same pattern: mandatory pre-task gate plus unconditional deference.

**Observed behavior:**

The agent calls `manage_skills list` at the start of nearly every session that has skills present. On tasks with a larger skill index, this is 2-4 extra rounds before user work starts. Combined with the "Agent prompt/context bloat" and "Skill/tool prompt-injection audit" ROADMAP items, this represents a significant source of per-request token overhead and agent-round waste.

**Expected behavior:**

- `manage_skills` is consulted when the domain looks relevant to an existing skill, not before every task.
- Skills are presented as candidate procedures to evaluate, not proven procedures to follow unconditionally.
- Draft skills are framed as candidates from prior sessions, not as authoritative guidance.

**Affected file:** `src/agent_loop.py`: three string literals (manage_skills tool description, matched-skills injection header, skill index block header)
