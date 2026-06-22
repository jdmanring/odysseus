# Skill System Architecture

This document is the canonical reference for the Brain → Skills pipeline in Odysseus.
It covers the complete data flow, every file that participates, every field, the design
decisions behind each component, and the research basis for those decisions.

---

## Research Foundation

The following papers informed the current design and the correctness work documented here.
All are freely available on arxiv.

| Ref | Paper | Key Finding Applied to Odysseus |
|-----|-------|--------------------------------|
| [1] | Voyager — `2305.16291` (Wang et al., 2023) | Foundational skill library for embodied agents; validates the core accumulate-and-reuse premise. |
| [2] | SkillsBench — `2602.12670` (2025) | **Curated** skills raise pass rate +16 pp. Self-generated skills with no curation provide zero benefit. The audit IS the quality gate — it must be able to promote passing skills. |
| [3] | SkillOps — `2605.13716` (2025) | Five diagnostic dimensions for skill library health: Utility, Redundancy, Compatibility, Failure-Risk, Validation-Gap. All five signals already exist in Odysseus sidecar data. |
| [4] | SkillBrew — `2605.29440` (2025) | Multi-objective curation: utility, coverage, diversity. Bi-level propose-then-verify. Validates Odysseus's self-edit-then-teacher-rewrite audit cycle. |
| [5] | AutoSkill — `2603.01145` (2025) | Lifelong extraction with Add/Merge/Discard maintenance. Validates deduplication-at-ingestion. |
| [6] | SkillWeaver — `2504.07079` (2025) | +31.8% on WebArena. Strong→weak model skill transfer adds +54.3%. Teacher-written skills must be available immediately — their value is enabling the student to retry on the next turn. |
| [7] | Skill Retrieval Benchmark — `2604.24594` (2025) | Hybrid BM25 + embeddings outperforms pure Jaccard or pure dense retrieval for procedural skill matching. |
| [8] | Graph of Skills — `2604.05333` (2025) | Skill dependency graphs. Odysseus's `requires_toolsets` / `fallback_for_toolsets` frontmatter fields are a primitive version of this. |
| [9] | SkillRet — `2605.05726` (2025) | Large-scale retrieval benchmark. Confirms BM25 hybrid. Distinctive vocabulary (tool names, domain terms) matters more than common terms. |
| [10] | ProcMEM — `2602.01869` (2025) | Score-based maintenance prunes low-return skills. Validates confidence-based demotion after audit failure. |

---

## Complete Pipeline

```
Agent run completes
       │
       ▼ (if rounds ≥ 2 AND tools ≥ 3)
── EXTRACTION ────────────────────────────────────────────────────────
   File: services/memory/skill_extractor.py
   Entry: maybe_extract_skill()

   • Last 12 messages → SKILL_EXTRACT_PROMPT → LLM → JSON
   • Drop if confidence < MIN_CONFIDENCE (0.85)
   • Drop if duplicate title (case-insensitive)
   • Save as DRAFT status (always; auto_approve_skills has no effect here)
   • Fire event "skill_added"
       │
       ▼ (event: skill_added)
── AUDIT ─────────────────────────────────────────────────────────────
   File: routes/skills_routes.py
   Entry: _audit_one_skill()

   Stage 1 — Necessity check (ADVISORY)
     LLM judge: is this skill unique and necessary vs existing library?
     Hit → flags in UI (_usage.json:necessity), never auto-acts alone.

   Stage 2 — Generic/duplicate blockers (BLOCKING)
     _skill_generic_blocker(): does skill match only trivial/common tasks?
     _skill_duplicate_blocker(): name/description similarity > threshold?
     Hit → demote to draft, set confidence=0.35, stop.

   Stage 3 — Retrieval precision check (ADVISORY)
     Does skill's when_to_use scope match a narrow query well?
     Broad scope → flag for narrowing, not block.

   Stage 4 — Functional test
     Run skill procedure in agent loop → LLM judge grades transcript.
     ├── pass (confidence=0.95) → auto-publish if auto_approve_skills=True
     ├── needs_work → self-edit → re-test
     │       ├── pass after edit (confidence=0.85) → auto-publish if allowed
     │       └── still fail → teacher escalation (if teacher_model configured)
     │               ├── pass after teacher (confidence=0.80) → auto-publish
     │               └── still fail → demote draft, confidence=0.35
     └── inconclusive → leave confidence, demote to draft
       │
       ▼ (for published skills, per-request)
── INJECTION ─────────────────────────────────────────────────────────
   File: src/agent_loop.py (lines ~1230–1264)

   • Load all skills for owner
   • Pre-filter based on auto_approve_skills pref (default True):
       True  → all skills pass to get_relevant_skills() at confidence floor
       False → published skills + source=teacher-escalation drafts only
   • get_relevant_skills(query, threshold=0.25, max_items=3, min_conf=0.85)
   • Jaccard token score × confidence boost × uses boost
   • Inject top N as "candidate procedures" in untrusted user-role message
       │
       ▼ (when injected)
── USE SIGNAL ────────────────────────────────────────────────────────
   File: services/memory/skills.py → record_use()

   • Increments uses counter in _usage.json
   • This is injection-use (matched + surfaced), not application-use
       │
       ▼ (nightly scheduler, 8 least-recently-audited per run)
── RE-AUDIT ──────────────────────────────────────────────────────────
   File: routes/skills_routes.py → run_scheduled_skill_audit()

   Same audit pipeline as above. Published skills that fail are demoted
   to draft. Prevents quality degradation over time.
```

---

## Files and Their Roles

| File | Role |
|------|------|
| `services/memory/skill_extractor.py` | LLM-based extraction from conversation history |
| `services/memory/skills.py` | `SkillsManager`: CRUD, `get_relevant_skills()`, field parsing |
| `routes/skills_routes.py` | Audit pipeline, REST API, audit scheduler |
| `routes/chat_helpers.py` | Outer extraction gate (checks rounds + tools before triggering extractor) |
| `src/agent_loop.py` | Per-request injection: pre-filter, `get_relevant_skills()`, prompt assembly |
| `src/tool_implementations.py` | `manage_skills` tool handler: add/view/list/search/delete from agent |
| `src/teacher_escalation.py` | Teacher model fallback: rewrites failed skills, writes with source=teacher-escalation |
| `data/skills/<owner>/` | SKILL.md files (frontmatter + body) |
| `data/skills/<owner>/_usage.json` | Sidecar metrics (uses, audit_verdict, necessity, timestamps) |

---

## Field Map

### SKILL.md frontmatter

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Kebab-case slug, unique per owner |
| `description` | string | One-line summary used in search |
| `version` | string | Semver |
| `category` | string | Grouping label |
| `tags` | list[str] | Searchable keywords |
| `platforms` | list[str] | OS/environment constraints |
| `requires_toolsets` | list[str] | Required capabilities |
| `fallback_for_toolsets` | list[str] | Alternative procedure when toolset missing |
| `status` | enum | `draft` or `published` |
| `confidence` | float | Quality signal; set by extractor/audit (see scale below) |
| `source` | enum | `learned`, `taught`, `imported`, `teacher-escalation` |
| `teacher_model` | string | Model ID used in teacher escalation (if any) |
| `owner` | string | User ID |
| `created` | datetime | ISO 8601 |
| `when_to_use` | string | Trigger description for retrieval |
| `procedure` | list[str] | Ordered steps |
| `pitfalls` | list[str] | Known failure modes |
| `verification` | list[str] | How to confirm success |
| `body_extra` | string | Free-form appendix |

### _usage.json sidecar (keyed `owner::name`)

| Field | Type | Description |
|-------|------|-------------|
| `uses` | int | Injection-use count (incremented when matched and surfaced) |
| `last_used` | datetime | Last injection timestamp |
| `audit_verdict` | enum | `pass`, `fail`, `needs_work`, `inconclusive`, `skipped`, null |
| `audit_by_teacher` | bool | Whether teacher model was used in the audit |
| `audit_worker_model` | string | Model ID used for functional test |
| `audit_teacher_model` | string | Model ID of the teacher (if any) |
| `audited_at` | datetime | Last audit timestamp |
| `necessity` | object | `{necessary: bool, redundant_with: list[str], reason: str}` |

---

## Confidence Scale

| Value | Meaning |
|-------|---------|
| 0.95 | Passed audit on first attempt (no edits needed) |
| 0.85 | Passed after one self-edit cycle |
| 0.80 | Passed after teacher model rewrote procedure |
| 0.60–0.84 | Low confidence; pre-audit or inconclusive |
| 0.35 | Failed audit; demoted to draft |
| 0.0 | Marked unnecessary/redundant by necessity check + generic blocker |

---

## `auto_approve_skills` — Semantics and Call Sites

This preference controls two things:

1. **Audit promotion** (`skills_routes.py`): whether a skill that passes the audit is
   automatically published. When `True` (default), the audit is the quality gate and
   acts on its verdict. When `False`, the audit is informational — it runs but never
   promotes; the user must publish manually from Brain > Skills.

2. **Injection scope** (`agent_loop.py`): which skills can appear in the agent prompt.
   When `True` (default), published skills and all drafts at the confidence floor are
   eligible. When `False`, only published skills and `source=teacher-escalation` drafts
   are eligible (the source-aware pre-filter preserves the teacher→student transfer path
   even in manual-review mode).

Extraction is NOT controlled by this preference. Extraction always produces draft skills.
The setting has no effect at extraction time.

| File | Line | Context | Correct Default |
|------|------|---------|-----------------|
| `services/memory/skill_extractor.py` | ~264–277 | Previously had pref check; correct behavior: always draft | **No pref check** |
| `src/agent_loop.py` | ~1242 | Injection gate | **`True`** |
| `routes/skills_routes.py` | ~504 | Audit promotion gate | **`True`** |
| `src/tool_implementations.py` | ~241 | `manage_skills add` fallback status | **`"draft"` (no pref check)** |

---

## Retrieval: `get_relevant_skills()`

**File:** `services/memory/skills.py:645–716`

Current implementation uses Jaccard token similarity with multiplicative boosts:
- Tag exact-match boost: `× 1.3` if all tag tokens in query
- Description substring match: sets `score = max(score, 0.6)`
- Confidence boost: `× (1.0 + confidence × 0.1)`
- Uses boost: `× 1.05` if `uses > 0`

**Threshold:** `0.25` (injection path), `0.3` (search API)
**Max items:** `3` (injection, configurable via `skill_max_injected` pref)

**Retrieval gap (Phase 2 target):** Jaccard fails on low-overlap but relevant queries.
Skills with distinctive procedural vocabulary ("libvirt", "nftables", "pyproject.toml")
are not surfaced by Jaccard when query uses synonyms or partial terms. BM25 weights
distinctive tokens higher and handles this correctly. Per SkillRet [9] and [7], hybrid
BM25+Jaccard significantly outperforms pure Jaccard for procedural skill retrieval.

---

## Teacher Escalation

**File:** `src/teacher_escalation.py`

When the student model (primary chat model) fails a task during the functional audit,
the teacher model (configured in Settings > Brain) is invoked to rewrite the skill
procedure. The teacher prompt template suggests `"confidence": 0.9` for the revised
skill (lines ~195 and ~293). Teacher-written skills are saved with `source=teacher-escalation`.

**Design intent (SkillWeaver [6]):** The teacher→student transfer mechanism only works
if the student can find the skill on the next attempt. This requires prompt injection
without a manual publish click. The injection path must therefore allow teacher-escalation
drafts to clear the confidence gate and appear in the agent context — before the user
has reviewed and published them.

The `skills.py:get_relevant_skills()` confidence gate (lines ~668–687) handles this:
- Published skills always pass
- Teacher-escalation drafts fail-closed on missing/garbage confidence (must have explicit
  numeric confidence ≥ floor to inject — this prevents untrusted teacher output from
  injecting without any quality signal)
- Other drafts are lenient on missing confidence (legacy skills don't silently vanish)

---

## Audit Pipeline Detail

**File:** `routes/skills_routes.py`

### Entry points

| Function | Trigger | Description |
|----------|---------|-------------|
| `_audit_one_skill(owner, name)` | `skill_added` event, POST /api/skills/audit | Full 4-stage audit on a single skill |
| `run_scheduled_skill_audit()` | Nightly scheduler | Audits 8 least-recently-audited skills |

### `_audit_finalize_status()`

Receives audit result and decides whether to promote. Key inputs:
- `auto_publish: bool` — from `auto_approve_skills` pref (default `True`)
- `verdict: str` — from functional test
- `confidence: float` — post-audit value
- `min_conf: float` — from `skill_min_confidence` pref (default 0.85)

Publishes only when: `auto_publish AND verdict == "pass" AND confidence >= min_conf`.

If `auto_publish=False`, a skill with perfect audit results (pass, 0.95 confidence,
necessary=True) remains as draft. Per SkillsBench [2], this produces zero benefit from
the audit pipeline — equivalent to never auditing.

---

## Extraction Gate

**File 1:** `routes/chat_helpers.py` — outer gate
**File 2:** `services/memory/skill_extractor.py:maybe_extract_skill()` — inner gate

Both gates use AND logic: `rounds >= 2 AND tools >= 3`. Sessions with fewer than 2
agent rounds or fewer than 3 tool calls do not qualify for extraction. This prevents
extraction from trivial housekeeping tasks (e.g., a single file read).

`MIN_CONFIDENCE = 0.85` in `skill_extractor.py` aligns with the injection floor.
Skills below this threshold are dropped at extraction rather than saved as dead weight
that will never inject.

---

## Gap Log (Outstanding Technical Debt)

| ID | Description | Target |
|----|-------------|--------|
| G1 | Pure Jaccard retrieval; BM25 would significantly improve matching | Phase 2 |
| G2 | No composite health score surface in UI; SkillOps signals exist but aren't aggregated | Phase 2 |
| G3 | `uses` counter counts injection-use, not application-use; agent doesn't report back | Future |
| G4 | No skill Merge operation (AutoSkill [5]): similar skills accumulate instead of merging | Future |
| G5 | No skill dependency graph (Graph of Skills [8]) | Future |
| G6 | `requires_toolsets`/`fallback_for_toolsets` fields not used by retrieval gate | Future |
