# Issue Draft: feat/skill-quality-signals -> odysseus-dev/odysseus

**Fork issue:** [#87](https://github.com/jdmanring/odysseus/issues/87)
**Branch:** `jdmanring/odysseus:feat/skill-quality-signals`

---

## Title

`feat(skills): BM25 hybrid retrieval scoring + composite skill health score`

---

## Body

### Problem

The `get_relevant_skills()` retrieval function uses pure Jaccard similarity over a
token bag. Jaccard treats all token overlaps equally: "configure", "the", "a", and
"libvirt" contribute identically if they appear in both the query and a skill's text.
This degrades precision for domain-specific queries: a query for "configure libvirt XML
bridge networking" will score equally against a skill about libvirt VM bridge setup and
one titled "configure application settings" if they share the common tokens.

The SkillRet benchmark (arxiv:2605.05726, 2025) and the Skill Retrieval Benchmark
(arxiv:2604.24594, 2025) both show that BM25-based retrieval significantly outperforms
pure Jaccard for skill libraries. BM25 assigns lower IDF weight to terms that appear in
many skills (common terms), and higher weight to rare, domain-specific terms (tool names,
library names, specific command vocabulary). This is the signal that matters for
identifying a skill's unique executable capability.

Additionally, the Brain > Skills UI exposes no single signal that summarizes a skill's
overall health. Confidence alone is insufficient: a skill with confidence=0.9 that has
never been used and failed necessity review reads the same as one with the same
confidence that has been used 15 times and passed necessity check. The SkillOps paper
(arxiv:2605.13716, 2025) proposes five diagnostic dimensions for skill library
maintenance; four of these (Utility, Validation, Reliability, Redundancy) are directly
observable from existing sidecar fields in `_usage.json` and skill frontmatter.

### Fix

**1. BM25 hybrid retrieval in `get_relevant_skills()`**

Replace pure Jaccard scoring with a `0.5 * Jaccard + 0.5 * BM25_norm` hybrid.

- `_compute_idf(skills)` builds an inverse document frequency table over the query-
  candidate corpus. O(N x L) where N = skill count, L = average token count per skill.
  Common terms (appearing in many skills) get low IDF weight; rare domain terms get
  high weight.
- `_bm25_score(query_tokens, skill_tokens, idf)` computes standard BM25 relevance
  (k₁=1.5, b=0.75, average document length derived from corpus). Raw score is
  unbounded.
- BM25 normalization: `bm25_raw / (bm25_raw + 3.0)` maps to [0, 1) without
  distorting inter-skill rankings.
- Hybrid combination: `0.5 * jaccard + 0.5 * bm25_norm`. Existing boosts (tag match,
  confidence multiplier, uses multiplier) apply on top of the hybrid base score.
- IDF is cached on `SkillsManager._idf_cache` and invalidated on `add_skill()`,
  `update_skill()`, `delete_skill()`. One cache miss on first retrieval per session,
  then O(1) per call.

**2. Composite health score in `load_all()` / `to_dict()`**

New `_health_score(skill) -> int` function derives a 0-100 integer from existing fields:

| Signal | Points | Source field |
|--------|--------|--------------|
| `confidence` | 0-40 | frontmatter `confidence` x 40 |
| `audit_verdict` | 0-30 | pass=30, inconclusive=15, needs_work=10, skipped=5, fail=0 |
| `uses` (capped at 20) | 0-20 | `_usage.json` `uses` |
| `necessity.necessary` | 0 or 10 | `_usage.json` `necessity.necessary` (absent = assume yes) |

No new data is stored. The health score is computed on read in `load_all()` after the
sidecar fields are merged. It propagates through the existing skill serialization
path to the API response automatically.

**3. UI badge on Brain > Skills cards**

`_healthBadge(sk)` renders a compact color-coded badge alongside the confidence %:

- Green (>= 80): high-health skill: well-audited, frequently used, necessary
- Yellow (60-79): moderate health: may benefit from re-audit or broader use
- Red (< 60): low-health: failed audit, unused, or unnecessary

The badge includes a tooltip with the numeric score and the four contributing factors
so users can identify which dimension is dragging the score down.

### Research Basis

- **SkillRet** (arxiv:2605.05726, 2025): BM25 hybrid outperforms pure Jaccard for
  skill retrieval. Skills are "executable capability packages"; retrieval must identify
  procedural intent, not just semantic similarity.
- **Skill Retrieval Benchmark** (arxiv:2604.24594, 2025): confirms hybrid BM25 approach
  across a large-scale benchmark of real agent skill libraries.
- **SkillOps** (arxiv:2605.13716, 2025): five diagnostic dimensions for skill library
  maintenance. Four map directly to existing Odysseus sidecar fields.

### Files Changed

- `services/memory/skills.py`: `_compute_idf()`, `_bm25_score()`, `_health_score()`
  helpers; `_idf_cache` on `SkillsManager`; cache invalidation in `add_skill()`,
  `update_skill()`, `delete_skill()`; `health_score` in `load_all()`; hybrid scoring
  in `get_relevant_skills()`
- `static/js/skills.js`: `_healthBadge()` function; badge added to skill card stats span
- `tests/test_skill_retrieval_bm25.py`: 7 new tests (NEW FILE)

### Labels

`enhancement`, `skills`, `brain`

---

## Filing Notes

- File after `fix/skill-lifecycle-correctness` (#86); the retrieval improvement
  assumes a healthy pipeline (correct defaults, functional audit promotion).
- Reference ROADMAP item: "Skills quality and curation tooling".
- No schema changes; no migration needed.
