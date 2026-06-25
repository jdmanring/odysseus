# PR Draft: feat/skill-quality-signals → pewdiepie-archdaemon/odysseus

**Fork issue:** [#87](https://github.com/jdmanring/odysseus/issues/87)
**Branch:** `feat/skill-quality-signals`
**Origin:** `upstream-mirror` (latest sync point)
**File this after:** `fix/skill-lifecycle-correctness` (audit pipeline must be functional)

---

## Title

`feat(skills): BM25 hybrid retrieval scoring and composite skill health score`

---

## Body

### Summary

Two improvements to the Brain > Skills quality layer:

1. **BM25 hybrid retrieval** — `get_relevant_skills()` now scores using `0.5 * Jaccard + 0.5 * BM25_norm`. Skills with distinctive vocabulary (specific tool names, domain terms, command syntax) score higher for domain-specific queries; generic filler terms no longer get equal weight to rare procedural tokens.

2. **Composite health score** — a new 0–100 `health_score` field in the skill card API response, derived from four existing sidecar signals (confidence, audit verdict, use count, necessity). Rendered as a color-coded badge on Brain > Skills cards.

Neither change modifies the SKILL.md schema or `_usage.json` format — all signals are read from existing fields.

---

### Motivation and Research Basis

**Retrieval**

Pure Jaccard similarity treats all token overlaps equally. A query for
`"configure libvirt XML bridge networking"` scores a libvirt-specific skill and a
generic "configure application settings" skill nearly identically if they share three
common tokens. BM25 assigns IDF weight to each token based on how many skills contain
it — specific tool names and domain vocabulary score higher.

The SkillRet benchmark (arxiv:2605.05726, 2025) and Skill Retrieval Benchmark
(arxiv:2604.24594, 2025) demonstrate that BM25 hybrid retrieval significantly
outperforms pure Jaccard for skill libraries. Their core finding: skills are "executable
capability packages" — retrieval must recognize procedural intent, which correlates
with distinctive vocabulary, not just semantic overlap.

**Health score**

SkillOps (arxiv:2605.13716, 2025) proposes five diagnostic dimensions for skill library
maintenance: Utility (usage frequency), Redundancy (duplicate detection), Compatibility,
Failure-Risk (execution reliability), Validation-Gap (missing quality checks). Four of
these map directly to existing Odysseus sidecar fields. A composite score surfaces
what is otherwise invisible: a skill with confidence=0.9 that failed the necessity
check and has zero uses needs different treatment than one with confidence=0.9, 20 uses,
and a pass verdict.

---

### Changes

#### `services/memory/skills.py`

**New helpers (module-level):**

`_compute_idf(skills: List[Dict]) -> Dict[str, float]`
- Computes inverse document frequency over the candidate skill corpus
- IDF formula: `log((N - df + 0.5) / (df + 0.5) + 1.0)` (smoothed BM25 variant)
- Tokens drawn from `name`, `description`, `when_to_use`, `tags` fields

`_bm25_score(query_tokens, skill_tokens, idf, k1=1.5, b=0.75, avg_len) -> float`
- Standard BM25 term frequency weighting
- Returns raw (unbounded) score; caller normalizes

`_health_score(skill: Dict) -> int`
- Derives 0–100 integer from existing sidecar fields
- Breakdown: `confidence×40` + audit verdict (pass=30/inconclusive=15/needs_work=10/skipped=5/fail=0) + `min(uses,20)/20×20` + necessity (absent/True=+10, False=+0)
- Handles None/missing fields without raising

**`SkillsManager.__init__`:**
- `self._idf_cache: Optional[Dict[str, float]] = None`

**Cache invalidation:**
- `self._idf_cache = None` added to `add_skill()`, `update_skill()`, `delete_skill()`

**`load_all()` (called by `to_dict()`):**
- `d["health_score"] = _health_score(d)` added after usage sidecar fields are merged

**`get_relevant_skills()` — hybrid scoring loop:**
```python
# Before scoring loop: build IDF cache and per-skill token lists
if self._idf_cache is None:
    self._idf_cache = _compute_idf(skills)
idf = self._idf_cache
token_lists = [list(_tokenize(full_text_for(sk))) for sk in skills]
avg_len = sum(len(t) for t in token_lists) / len(token_lists) if token_lists else 60.0

# In scoring loop (replaces pure Jaccard):
jaccard = _jaccard(query_tokens, set(skill_tokens))
bm25_raw = _bm25_score(query_tokens, skill_tokens, idf, avg_len=avg_len)
bm25_norm = bm25_raw / (bm25_raw + 3.0) if bm25_raw > 0 else 0.0
score = 0.5 * jaccard + 0.5 * bm25_norm
# Existing tag/confidence/uses boosts applied on top (unchanged)
```

#### `static/js/skills.js`

**`_healthBadge(sk)` function** (new, after `_confColor()`):
```javascript
function _healthBadge(sk) {
  const h = typeof sk.health_score === 'number' ? sk.health_score : null;
  if (h === null) return '';
  const color = h >= 80 ? 'color-mix(in srgb, #4ade80 60%, transparent)'
              : h >= 60 ? 'color-mix(in srgb, #f0ad4e 60%, transparent)'
              :            'color-mix(in srgb, #f87171 60%, transparent)';
  return `<span class="memory-cat-badge" title="Health score: ${h}/100 (confidence + audit verdict + uses + necessity)" style="background:${color};font-size:0.72em;padding:1px 5px;cursor:default;">${h}</span>`;
}
```

Stats span in skill card template updated to:
```javascript
<span class="skill-stats">${_auditMarks(sk)}<span class="skill-conf" style="color:${confColor};">${conf}%</span> · ${uses}u ${_healthBadge(sk)}</span>
```

#### `tests/test_skill_retrieval_bm25.py` (NEW FILE — 7 tests)

| Test | What it verifies |
|------|-----------------|
| `test_bm25_ranks_distinctive_skill_higher` | BM25 scores libvirt-specific skill > generic "configure settings" skill for a libvirt query |
| `test_bm25_returns_zero_for_no_overlap` | BM25 returns 0.0 for a query with no corpus token overlap |
| `test_hybrid_get_relevant_skills_empty_list` | Empty skills list → empty result, no exception |
| `test_hybrid_get_relevant_skills_retrieves_distinctive` | Hybrid `get_relevant_skills()` returns distinctive skill first (threshold=0.0) |
| `test_health_score_ideal_skill_is_100` | confidence=1.0, pass verdict, 20 uses, necessary → score=100 |
| `test_health_score_failed_skill_is_low` | confidence=0.35, fail verdict, 0 uses, unnecessary → score<30 |
| `test_health_score_handles_missing_fields` | `_health_score({})` and None fields do not raise; result is 0–100 |

All 7 tests pass. Full skill test suite: 40 passed.

---

### Non-Changes

- SKILL.md schema: no changes
- `_usage.json` format: no changes
- Audit pipeline: no changes
- Existing scoring boosts (tag, confidence, uses multipliers): behavior unchanged, applied after hybrid score
- Threshold and max_items parameters: unchanged

---

### Manual Verification Steps

1. **BM25 retrieval improvement:**
   With a published skill named "configure-libvirt-xml-bridge" and a generic
   "configure-application-settings" skill both in the library, send a query
   `"configure libvirt xml bridge networking"` through any agent turn.
   Confirm the libvirt-specific skill appears in the injected candidates, ranked first.

2. **Generic skill does not contaminate domain query:**
   Same setup — confirm the "configure-application-settings" skill does not appear
   in the top-3 injected candidates for the libvirt-specific query.

3. **Health score badge on skill cards:**
   Open Brain > Skills. Confirm each skill card shows a colored badge (green/yellow/red)
   next to the confidence percent. Hover the badge to confirm the tooltip shows
   `"Health score: N/100 (confidence + audit verdict + uses + necessity)"`.

4. **Health score color thresholds:**
   A skill with confidence=0.95, pass verdict, ≥20 uses, necessary=True should show
   green (score ≥ 80). A skill with confidence=0.35, fail verdict, 0 uses should show
   red (score < 60).

5. **IDF cache invalidation:**
   Add a new skill via Brain > Skills. Trigger a retrieval-dependent agent turn.
   Confirm no Python error about stale IDF (i.e., the new skill's tokens are
   represented in retrieval scoring).

6. **Tests:**
   ```bash
   python -m pytest tests/test_skill_retrieval_bm25.py -v
   python -m pytest tests/ -q  # confirm no regressions in 4441-test suite
   ```

---

## Filing Notes

- File the upstream issue first; reference the issue number in the PR.
- File after `fix/skill-lifecycle-correctness` has been filed and reviewed — retrieval
  improvement is most meaningful when the audit pipeline is functional.
- Base branch: `dev` (upstream default development branch).
- No migration needed. No config changes needed.
- Reference ROADMAP item: "Skills quality and curation tooling".
