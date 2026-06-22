# Upstream Issue Draft: fix-skill-extraction-threshold

**File on:** `pewdiepie-archdaemon/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/fix-skill-extraction-threshold.md`
**Branch:** `fix/skill-extraction-threshold`
**Type:** Bug
**Fork issue:** jdmanring/odysseus#84

---

## Title

`fix(skills): extraction threshold too low and auto-approve default publishes unreviewed skills`

---

## Body

**Install method:** Docker / manual Python

**OS / device:** Any

**Problem 1 — Extraction gate fires on trivially short sessions:**

The gate in `routes/chat_helpers.py` triggers when `agent_rounds >= 2 OR agent_tool_calls >= 2`. Nearly every non-trivial agent interaction qualifies — a task that reads a file and writes it back (2 tool calls, 1 round) is enough. The corresponding gate in `services/memory/skill_extractor.py` uses the same OR logic. This is not selective enough to identify genuinely reusable procedures; it extracts from routine housekeeping tasks.

**Problem 2 — Confidence threshold mismatch creates zombie skills:**

`MIN_CONFIDENCE = 0.6` in `skill_extractor.py` saves skills to disk. The injection gate in `agent_loop.py` defaults to `skill_min_confidence = 0.85`. Skills with confidence 0.60–0.84 are saved but never surfaced to the agent. They accumulate in `data/skills/` as dead weight, growing the storage footprint without contributing to agent capability.

**Problem 3 — `auto_approve_skills` defaults to `True`:**

Extracted skills are auto-published without user review. A skill extracted from a failed or one-off session immediately becomes part of the agent's injected context on the next turn. The user has no gate to prevent a low-quality extraction from affecting agent behavior.

**Observed result:**

Low-quality skills (libvirt XML configuration procedures, etc.) appear in `data/skills/` from routine agent tasks. Each extracted skill adds to the skill index, increasing prompt token usage on every subsequent agent request. Combined with the ROADMAP item "Agent prompt/context bloat", this is a compounding problem: every session grows the index, which grows the prompt, which reduces available context.

**Expected behavior:**

- Extraction triggers only for sessions that show genuine multi-step complexity: at least 2 rounds AND at least 3 tool calls.
- Skills with confidence below the injection floor (0.85) are not saved to disk.
- Extracted skills land as drafts; the user reviews and publishes from Brain > Skills.

**Affected files:**
- `services/memory/skill_extractor.py` — `MIN_CONFIDENCE`, extraction gate condition, `auto_approve_skills` default
- `routes/chat_helpers.py` — outer extraction gate condition
