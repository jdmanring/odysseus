# Plan: consolidate "is this model downloaded?" into one canonical predicate (#121)

Fork issue: [#121](https://github.com/jdmanring/odysseus/issues/121). Classification:
**upstream-candidate** (shared `static/js/cookbook*.js`). Branch from `upstream-mirror`.
**Implemented** on `fix/model-downloaded-detection` (`c17973f2`), cherry-picked to develop.

On `upstream-mirror` the duplication was 4 sites in `cookbook-hwfit.js` (not the 16 that
develop's fork patches had inflated it to); develop additionally carried a second re-mark
loop, also consolidated during the cherry-pick. The canonical `isModelDownloaded` accepts
a model object, a bare id string, or an id array (the row re-mark stores identities on the
row as `data-dl-ids` to stay gguf-aware from the DOM). Proven: the better-quant lock case
returns `false` under the old name-only logic and `true` under the predicate.

## Problem (why it keeps regressing)

Installed local models stop greying out in the Cookbook "What Fits?" catalog after
download. It has been fixed at least three times (`75ff98b8`, `15d2666f`, `a551417e`) and
returns each time. The cause is not a wrong rule; it is **duplication**: the decision
"is this catalog model downloaded?" is reimplemented ~16 times across three files with
divergent logic, and only three copies handle the auto-discovered-quant case.

| File | match sites | `gguf_sources`-aware |
|------|-------------|----------------------|
| `static/js/cookbook-hwfit.js` | 13+ (`dlDot`, card-greying `_downloaded`, row re-mark, serve gate) | 3 only |
| `static/js/cookbook.js` | 3 | 0 |
| `static/js/cookbook-diagnosis.js` | 1 | 0 |

`_cachedModelIds` is a `Set` of downloaded `repo_id`s (from `/api/model/cached`). The dot
(`dlDot`) checks `name`, short name, **and every `gguf_sources` repo**; the card-greying
copy checks only `name` + `endsWith('/'+short)`. So the dot lights but the name never greys.

**Trigger (fork-amplified):** the fork's quality-scored GGUF discovery
(`fix/gguf-quality-scored`) resolves a community quant repo (e.g.
`bartowski/Meta-Llama-3.1-8B-GGUF`) when a catalog model has no static `gguf_source`. The
downloaded `repo_id` is then that quant repo, **not** the catalog `name`, so every
name-only matcher copy fails. Upstream leans on static `gguf_sources` and hits this less,
which is why this is felt acutely in the fork but the *defect* (duplication) is in shared
code.

Each historical fix patched a subset of the copies (`a551417e`: "in both code paths");
there are ~16 and nothing canonical to converge to. That is the whole bug.

## Upstream landscape (researched 2026-06-27)

Adjacent, none covering the client-side predicate:
- [#4049](https://github.com/odysseus-dev/odysseus/issues/4049) server cache
  unaware of installed models after update (server side).
- [#2342](https://github.com/odysseus-dev/odysseus/issues/2342) auto-discovered
  models without `gguf_sources` (the data gap our discovery answers).
- PRs [#3076](https://github.com/odysseus-dev/odysseus/pull/3076) (191 missing
  sources), [#2368](https://github.com/odysseus-dev/odysseus/pull/2368) (warn on
  missing source), [#2219](https://github.com/odysseus-dev/odysseus/pull/2219) /
  [#2993](https://github.com/odysseus-dev/odysseus/pull/2993) (cached-model
  serve/scan), [#368](https://github.com/odysseus-dev/odysseus/pull/368) (merged,
  gguf-only downloads). Discussion: "No GGUF source configured for Cookbook models".

These address *data* (missing sources) or *server* cache. The duplicated *client*
downloaded-predicate is unreported upstream and worth contributing.

## Prior art

**In-repo precedent (the template):** `static/js/model/matchKey.js` exports a single pure
`matchModelKey(name, keys)`. It exists because model-name lookups "returned the first
substring match" (`gpt-4o-mini` matched `gpt-4o`), the same class of matching regression,
and it is locked by a node-executed unit test (`tests/test_match_model_key_js.py`,
skipped when `node` is absent). We follow that pattern exactly: one pure matcher under
`static/js/model/`, one node test, all call sites import it.

**External:** package managers (apt/pip) answer "installed?" from one installed-set query,
never re-derived per view; Ollama/LM Studio/Jan match installed models by a canonical
identity (digest / base repo), not a display string. The durable shape is single
source of truth + canonical, quant-independent identity.

## Design

### 1. Canonical identity

A catalog `model` can be referred to by several ids; a downloaded `repo_id` may be any of
them. Define the candidate-id set for a model (quant-independent):

```
modelIdentities(model) -> Set<string>
  // full + short (last path segment) of each of:
  //   model.name, model.repo_id, model.quant_repo,
  //   every model.gguf_sources[].repo
```

Short (`x/y/z` -> `z`) is included because downloaded ids and catalog names are expressed
either way, but **full-id matches are preferred and short is a guarded fallback** (mirrors
the current `dlDot` ordering) to avoid short-name collisions across orgs.

### 2. The predicate

New module `static/js/model/downloaded.js`, pure and Qt/DOM-free (testable under node):

```js
export function isModelDownloaded(model, cachedIds) {
  if (!cachedIds || !cachedIds.size) return false;
  const ids = modelIdentities(model);
  // 1) any full id present
  for (const id of ids.full)  if (cachedIds.has(id))  return true;
  // 2) guarded short fallback: a cached id equals or endsWith('/'+short)
  for (const s of ids.short)
    for (const c of cachedIds) if (c === s || c.endsWith('/' + s)) return true;
  return false;
}
```

(Exact internal shape TBD at implementation; the contract is: complete union match,
full-before-short, gguf-aware.)

### 3. Replace all sites

Convert every `_cachedModelIds.has(...)` / `[..._cachedModelIds].some(...)` decision in
`cookbook-hwfit.js` (dlDot, card `_downloaded`, the `hwfit-list` row re-mark loop, the
serve gate, and the remaining ~9), `cookbook.js` (3), and `cookbook-diagnosis.js` (1) to
`isModelDownloaded(model, _cachedModelIds)`. Delete the divergent inline heuristics.

### 4. Tests (lock the regression)

- `tests/test_model_downloaded_js.py` (node-executed, pattern of `test_match_model_key_js.py`, `@pytest.mark.skipif(no node)`):
  - **The better-quant lock:** model `name = meta-llama/Meta-Llama-3.1-8B-Instruct`, no
    static source, `gguf_sources=[{repo:'bartowski/Meta-Llama-3.1-8B-Instruct-GGUF'}]`,
    cached `{bartowski/Meta-Llama-3.1-8B-Instruct-GGUF}` -> **true**. (This single case
    would have caught all prior regressions.)
  - Full-name match; short-name fallback; `quant_repo` match; nothing downloaded -> false;
    short-name collision across orgs does not false-positive on a full-id-only entry.
- `tests/test_no_adhoc_downloaded_match.py`: an **anti-reintroduction guard** (Python source
  audit): assert no raw `_cachedModelIds.has(` / `_cachedModelIds].some(` appears in
  `cookbook*.js` outside `downloaded.js`'s import sites. This is what ends the cycle: a new
  divergent copy fails CI.

## Implementation steps

1. Create issue #121 (done). Branch `fix/model-downloaded-detection` from `upstream-mirror`.
2. Add `static/js/model/downloaded.js` (`modelIdentities` + `isModelDownloaded`).
3. Add `tests/test_model_downloaded_js.py` (incl. the better-quant lock) and confirm it
   FAILS against the current card-greying logic first (prove it catches the bug), then
   passes against the new predicate.
4. Replace the ~16 sites across the three files; import the predicate.
5. Add `tests/test_no_adhoc_downloaded_match.py` guard.
6. Manual verify: install a model via auto-discovered quant (bartowski repo); confirm both
   the ● dot and the **name greying** update, and the serve gate treats it as downloaded.
7. Cherry-pick to develop (`-x`); branch retained for upstream PR. Stage PR/issue drafts.

## Acceptance

- One predicate; zero raw `_cachedModelIds` matches outside `downloaded.js` (guard test).
- Better-quant lock test green; would fail against the old card-greying copy.
- Live: an auto-discovered-quant install greys the name (not just the dot) everywhere
  (catalog card, dot, row re-mark, serve gate).
- Full suite green; cherry-picked to develop.

## Risks / edge cases

- **Short-name collisions** (two orgs, same short name): keep full-id preference; short is
  fallback only. Test guards this.
- **Ollama tags** (`llama3:8b`) and **partial/stalled** downloads: `_cachedModelIds` already
  filters `status !== 'stalled'`; the predicate operates on whatever ids the cache reports,
  so behavior is unchanged for those, covered by reusing the existing cache contract.
- **No build step / ES modules:** the new file is a plain ES module imported like
  `matchKey.js`; no bundler change. node only needed for the unit test (skipped if absent),
  matching existing convention.
- **Rollback:** isolated to one new module + mechanical call-site swaps; revert the module
  import per file if needed. No server/API change.
