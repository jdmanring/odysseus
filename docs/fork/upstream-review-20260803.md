# Upstream review: the 1,957 commits ingested 2026-08-02

Scope: `prengest-20260802-0131/upstream-mirror..upstream-mirror` — 1,957 commits,
**1,882 non-merge**, spanning 2026-07-18 to 2026-07-30.

Four questions, answered with measurements rather than impressions:

1. did resolving conflicts to our side regress anything of theirs?
2. what did they do better that we should adopt?
3. what did they ship that supersedes our staged work?
4. what should we do differently?

---

## Shape of the ingest

| type | count |
|---|---|
| (untyped, older upstream style) | 860 |
| fix | 823 |
| feat | 57 |
| refactor | 38 |
| test | 35 |
| docs | 30 |
| chore | 22 |
| ci | 11 |
| perf | 3 |
| security | 3 |

Top scopes: `cookbook` 54, `tests` 40, **`security` 32**, `agent` 31, `email` 26,
`chat` 21, `ui` 21, `auth` 18, `llm` 17, `calendar` 16.

This is overwhelmingly a **hardening** release, not a feature release: 823 fixes to
57 features. Security is the third-largest scope.

---

## 1. Did we regress anything of theirs?

Audited with `fork_work_loss.py` using explicit refs (the derived base is wrong
after promotion — see `sha-map-20260803-scrub.md`). **64 files, 422 dropped upstream
lines** across 1,694 scanned. Full output:
`docs/fork/audits/ingest-20260802-upstream-loss.txt`.

All but one are the fork's four standing divergences — ChromaDB→Qdrant,
hf_transfer→aria2c, stdlib-logging→structlog, and MessageWindow-over-pager. Several
are *actively asserted absent* by our own tests.

**One real regression, found and fixed:** upstream derives a download card's
provider logo from `task.payload.repo_id`; the merge resolved that hunk to the
fork's `task.name`. Fixed in `77f62ac7`.

**One near-miss:** upstream's `String.replace` `$&`-corruption fix in `markdown.js`
was dropped mid-merge, caught by `test_markdown_rendering_js`, and restored before
the merge commit.

**Security fixes verified INTACT**, not assumed — this was the highest-risk class:

| upstream hardening | develop | upstream |
|---|---|---|
| `check_outbound_url` SSRF callers | 8 | 8 |
| DNS-rebinding pinned-IP delivery | present | present |
| ReDoS-safe think/tool parsers | 9 files | 9 files |
| credential/PII log redaction | present | present |
| untrusted-wrap for MCP/email/integration descriptions | present | present |

43 SSRF/url-safety tests pass on develop.

---

## 2. What they did better — and one is ACTIONABLE ON A STAGED BRANCH

### ReDoS: forward-only delimiter scanning (ADOPT THIS)

Upstream shipped four ReDoS fixes (#4704, #4877, #4941, #4943). The technique in
`d62eba42` is the transferable part: a lazy `<tag>([\s\S]*?)</tag>` pattern driven by
`finditer` is **O(n^2)** on untrusted "many openers, no closer" output. They split
each into separate OPEN and CLOSE regexes and scan forward-only with `bisect`, which
keeps it near-linear.

**Our staged `fix/longcat-tool-parsing` reintroduces exactly that shape** in exactly
that file:

```python
_LONGCAT_TOOL_CALL_RE = re.compile(
    r"<longcat_tool_call>\s*([\s\S]*?)\s*</longcat_tool_call>", re.IGNORECASE)
...
for m in _LONGCAT_TOOL_CALL_RE.finditer(text):     # tool_parsing.py:1443
```

Measured on that exact pattern — clean quadratic growth:

| openers, no closer | time |
|---|---|
| 200 | 4.0 ms |
| 400 | 16.0 ms |
| 800 | 57.2 ms |
| 1600 | 241.7 ms |

Model output is untrusted input. Filing this branch as-is would regress a security
fix upstream had just landed in the same file, and their CodeQL
(`py/polynomial-redos`) would likely flag it in review. **Rework the pattern to
upstream's open/close split before filing.**

### SSRF: one guard, many callers

Upstream converged every outbound fetch on `src/url_safety.check_outbound_url` —
gallery, embeddings, CardDAV, reminder webhooks, integration `api_call`, skills
importer — rather than per-site checks, and pinned delivery to the validated IP to
close DNS rebinding. The pattern worth copying is the convergence: a single guard
with N callers is auditable; N checks are not.

### Case-insensitive deny-lists

Two separate fixes (#5097, #5189) for the same root cause: a sensitive-file deny
list that matched case-sensitively, so `.SSH/` slipped through. Applies to any
deny-list we write.

---

## 3. What they superseded — and where WE are ahead

**By patch-id, `branch_survey.py` reports 0 RETIRE**: upstream shipped an equivalent
for none of our ~80 staged branches. No branch is wholly obsolete.

**They superseded us once, and we adopted it:** the file-tool allowlist. Upstream
removed `$HOME` from the default roots; we had added it unconditionally. Their model
is better because an active workspace confines the agent to IT instead of the
default list, so the tightening costs no capability once a folder is chosen.
Adopted in `91c31113`, verified empirically, two mutation-tested regression tests.

**We are ahead of them here — file it upstream:** `src/model_context.py` known-model
matching. Upstream picks the longest matching key. Ours scores a basename match
double and strips `:free` / `:extended` suffixes, so a key matching the org prefix
cannot outrank one matching the actual model name (`anthropic/claude-…`). Strictly
better; upstream-candidate.

**Convergent evidence:** upstream and this fork independently wrote near-identical
analyses of the `String.replace` `$&`/`` $` ``/`$'`/`$$` substitution trap, down to
the same worked examples (`echo "$$USD"`). Two parties reaching the same fix
separately is the strongest signal available that the fix is right — and it is a
reason to prefer *their* wording when merging, since theirs is the one their
reviewers already accepted.

**Supersession risk by branch** (overlap between a branch's files and files upstream
changed) — full scan in the session record. Highest: `feat/memory-qdrant-nomic`
(13 files), `feat/aria2c-downloader` (8), `feat/logging` (7),
`fix/dom-oom-virtualization` (6), `feat/longcat-provider` (6). Overlap is a triage
signal, not a verdict; each was rebased and its own tests pass.

---

## 4. What we should do differently

**Verify a fix is still needed before rebasing it.** `fix/agent-context-budget-discovery`
was rebased before anyone read `pr-status.md`, which already said "Superseded by
upstream; do not file" — upstream shipped the same lazy-probe idea as #4886.

**Check the tracker before analysing a branch.** `refactor/assets-move` was declared
"unfileable, retire" on reasoning that was simply wrong; the correction required
reading what the branch actually does, scoped against the OLD mirror tag. Sampling
`git rev-list upstream-mirror..<branch>` on an un-rebased branch returns ~1,900
unrelated commits.

**A green check is not evidence until you know what it can detect.** The
post-promotion loss scan reported a confident zero because its derived base had
become `upstream-mirror` itself. It is now guarded (exit 2) rather than reassuring.

**Adopt upstream's security techniques proactively, not just their patches.** The
ReDoS finding above was only visible because the *technique* was read, not the
diff. Their four ReDoS commits are a checklist for every lazy regex we own.
