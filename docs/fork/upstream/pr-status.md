# Upstream Contributions

One branch per contribution. Each branch is built from `upstream-mirror` and contains
only the changes for that one fix or feature; nothing fork-specific.

**Never push to upstream remote. Never file issues or PRs upstream without explicit
per-action authorization. Agents stage; you file.**

---

## ⚠ 2026-08-03: rebase state after the 1,957-commit upstream ingest

**This supersedes the 2026-07-07 section below. Read this one first.**

**Mirror state:** `upstream-mirror` is at `fb8c391a` (upstream/dev, 2026-08-04)
after the 2-commit ingest of 2026-08-03 (LKG-20260803-2036), which was
**promoted to `develop` the same day** as merge `21a45b1f` (#180), after
`integration` was re-baselined onto the mirror plus the fork's protected files
(`104118b6`). The old mirror for that
ingest is tagged `preingest-20260803-2028/upstream-mirror` -- that is the
`--old-mirror` argument for any rebase sweep, and it cannot be recovered if lost.

The 1,957-commit ingest below took `upstream-mirror` to `25c9e735`
(upstream/dev, 2026-07-30). The merge into
`develop` was 182 conflicted files — see `docs/fork/ingest-20260802-resume.md`.

**The staged branches were rebased onto the mirror as it stood at `25c9e735`
(2026-08-02), 0 superseded-to-empty.** Read that carefully: they are NOT on the
current mirror. Verified 2026-08-04 -- only 4 refs descend from `fb8c391a`
(`develop`, `integration`, `upstream-mirror`, `fix/slash-memory-category-escape`);
the other 96 staged branches still fork at `25c9e735`. The 2026-08-03 ingest was
2 commits, so the gap is small, but "rebased onto the new upstream-mirror"
claimed a currency they do not have.

Rollback for every one at `refs/prerebase/<branch>` (86) and
`refs/prerebase2/<branch>` (3), **all 89 pushed to origin** -- the 3
`prerebase2` refs were local-only until 2026-08-04, while this document said
they were safe. Restore with `git update-ref refs/heads/<b> refs/prerebase/<b>`.

Count the refs rather than trusting a number in prose:
`git for-each-ref refs/prerebase refs/prerebase2 | wc -l` against
`git ls-remote origin 'refs/prerebase*' | wc -l`.

Tooling: `tooling/merge/branch_survey.py` (what is already landed, by patch-id),
`tooling/merge/rebase_staged.py` (batch rebase, dry-run by default),
`tooling/merge/verify_rebase.py` (did the rebase keep the branch's own work).

**Rebase the OLD mirror tag, never `merge-base`.** `upstream-mirror` is RESET, not
fast-forwarded, so `merge-base <branch> upstream-mirror` returns an ancient ancestor
and a 2-commit branch tries to replay ~1,900 commits. Use
`--onto upstream-mirror prengest-20260802-0131/upstream-mirror`.

### Status changes you must know before filing anything

| branch | change |
|---|---|
| `fix/longcat-tool-parsing` | **NOT the same branch as the row below.** Reworked 2026-08-03: its lazy `<longcat_tool_call>([\s\S]*?)</...>` under `finditer` was O(n^2) on untrusted model output — the exact ReDoS shape upstream had just eliminated in that file (#4704/#4877/#4941/#4943). Now on upstream's `_iter_delimited`; 3200 openers 947.7 ms -> 0.489 ms. 4 regression tests. |
| `feat/memory-hybrid-recall` | **NEW branch (#172)**, split out of `feat/memory-qdrant-nomic`. Backend-independent half — hybrid BM25+dense recall + write-time supersede. 109/109 on a pure upstream ChromaDB tree. File THIS rather than the Qdrant branch. Declares a contract change: `MemorySearchHit.score` is now fused, not raw vector similarity. |
| `fix/agent-context-budget-discovery` | Confirmed superseded by upstream #4886. Do not file, do not delete. |
| `refactor/assets-move` | Rebased; 11 MB of unreferenced `.gif` media dropped. The earlier "unfileable, retire" verdict was WRONG and is retracted. |
| `test/upstream-pr-4661` | Deleted — snapshot of a CLOSED-unmerged upstream PR that did not even match its head. Recoverable at `refs/deleted/`. |
| `fix/model-context-org-prefix` | **NEW branch (#173)**, staged 2026-08-03. We are ahead of upstream: their longest-key rule lets `moonshot` (len 8) beat `kimi-k2` (len 7) by matching the ORG portion of `moonshotai/kimi-k2.6`, budgeting 128k for a model served at 256k. Basename-weighted scoring fixes it. 3 regression tests, the two org-prefix ones mutation-checked against the old implementation. |
| `fix/dom-oom-virtualization`, `feat/aria2c-downloader` | Re-converged 2026-08-03 (`9f415298`, `8e1c18a8`). Guard #131 caught `static/app.js` and `static/js/cookbookRunning.js` lagging develop. Both green. |
| `fix/test-temp-db-leak` | **NEW branch (#174)**, staged 2026-08-03. The suite never removes its temp databases or directories: a full suite run leaks 29 databases, 23 directories and 8 data dirs, none removed; the branch leaks 0/0/0. Filled a RAM-backed /tmp until 10 Playwright tests failed with "Page crashed" and read as a code regression. **The accumulated counts first reported here (3,790 / 67,496) were withdrawn 2026-08-03: 98% of the directory figure was another project's artifacts on the same host.** Defect is upstream's (files byte-identical to `upstream-mirror`); origin is upstream #2930, which scoped cleanup out of a proving slice. PR + issue drafts written. |
| `fix/truncate-fork-by-msg-id` | Gained the commit now at `9ffeba0c` (cited here as `d75a4acc` until 2026-08-04; that SHA is the pre-rebase original and survives only at `refs/salvage/truncate-tempdb-fix`, on no branch -- same patch-id `01a3f374`, so the work is present): the module's own temp-db leak, the ONLY fork-authored one of 37. Written self-contained so the branch stays independently fileable; now under #131's convergence guard. |
| `fix/slash-memory-category-escape` | **NEW branch (#182)**, staged 2026-08-03, **rewritten 2026-08-04 after four independent reviews falsified its central claim.** As first written it reported an XSS whose reproduction does not fire: it claimed `category` is never validated server-side, when `MemoryAddRequest` (`src/request_models.py:42-47`) coerces anything outside a seven-value allowlist to `fact`. Two further claims were also false -- "sole output path" (`_eggRender` at `slashCommands.js:5314` is a second `innerHTML` sink with 10 callers) and "single-user, local-first" (real multi-user auth; memory is *owner-scoped*, which is the correct reason severity stays low). Now framed as what it is: defence in depth over four fields left raw beside escaped neighbours, one of them in an `href` attribute. Two of the four were found by the review, in the same file the first commit had just edited. Guards rewritten too -- the originals asserted four source literals and passed a variant carrying three live XSS holes. **File #184 first; this is the output half.** |
| `fix/memory-category-validation` | **NEW branch (#184)**, staged 2026-08-04, and **the one to file first.** `category` was validated on `POST /api/memory/add` and on neither of the other two write paths: `PUT /api/memory/{id}` (`routes/memory/memory_routes.py:512`) took a raw `Form` value and wrote it verbatim, and `mcp_servers/memory_server.py:161` did the same on the `source="ai_agent"` path, where the value is model-written and needs no user action. Both now apply the allowlist, coercing rather than rejecting to match `/add`. The allowlist existed twice -- a Python list and a regex alternation -- and is now one `MEMORY_CATEGORIES` constant. Scope is validation only: the idea of adding `/add`'s `require_privilege` guard to `PUT` was dropped after reading the router, since `DELETE` and pin guard with ownership alone too. 8 tests calling the real handler; mutation-checked. |
| `fix/session-route-test-flake` | **NEW branch (#175)**, staged 2026-08-03. Module-global `APIRouter` accumulates a route per `setup_session_routes()` call, so the test's `next(...)` picks an earlier test's endpoint bound to an empty mock. Fixed on develop by `670ee643` on **2026-07-22** and never staged; found by checking a claim written into the #174 draft. Reproduced twice on clean `upstream-mirror`: 1 failed/69 passed -> 70 passed. |
| `test/css-and-path-confinement-guards` | **NEW branch (#176)**, staged 2026-08-03. Structural guard for style.css (source-assertion tests cannot see brace depth; a broken file passed all 14) and allowlist guards for `src/tool_execution.py`. 30 passed on an unmodified tree. |

**Unstaged-work audit, 2026-08-03.** 3,019 develop commits, 45 on no staged
branch by patch-id, 39 of those fork-management. Of the remaining 6, two were
genuine unstaged contributions (now #176) and four restore upstream's own code
that the ingest merge dropped, so there is nothing to send back. Method:
`git log --no-merges -p | git patch-id --stable` in batch mode, two processes.
Re-run it after any large ingest.

### Supersession verdicts expire

A branch marked "superseded by upstream PR #N" is only superseded while #N is
open or merged. **When #N closes unmerged, our branch becomes the only fix and
should be filed.** Verified 2026-08-03 against every such claim here:

| cited | state | consequence |
|---|---|---|
| #1629 | MERGED | supersession holds |
| #2418 | **CLOSED** | `fix/streamingtts-scope` is fileable again — corrected above |
| #2930 | MERGED | holds (it is the origin of #174's helper) |
| #4661 | **CLOSED** | already recorded: the fork's memory implementation is the only one |
| #5290 | MERGED | holds |
| #4886 | is an ISSUE, not a PR, CLOSED, titled "Wrong context_length from OpenRouter endpoint" | the citation for `fix/agent-context-budget-discovery` **needs re-deriving**; the lazy-probe behaviour IS in the mirror (17 hits in `agent_loop.py`), so the conclusion may be right and the reference wrong |

Re-run this check after every ingest. `gh pr view <n> --repo odysseus-dev/odysseus
--json state` settles each one in a second, and a stale verdict costs a
contribution that upstream never received.

### Staged-branch inventory, 2026-08-03 (post-ingest)

105 non-trunk branches. **91 are rebased onto the current `upstream-mirror`**
(under 60 commits each); 14 carry ~1,845 inherited upstream commits and are
fork-only (`fork/`, `backup/`, `sync/`, `preingest`), so they are not filing
candidates. **None of the 91 has been superseded by the ingest** — no staged
branch's commits are already in upstream by patch-id.

**Draft coverage: 89 of 89 rebased branches now have a PR draft** (2026-08-03).
Two branches were deleted rather than drafted: `test/upstream-pr-4366` (snapshot
of a CLOSED upstream PR) and `perf/renderer-memory-reclaim` (strict subset of
`perf/qt-psi-graduated-reclaim`: zero unique commits). Both preserved under
`refs/deleted/`.

Every draft carries a test count **run on 2026-08-03**, not one recalled from a
commit message. Five branches have no test files and say so explicitly rather
than implying coverage. Three branches were RED when measured and were fixed
first, all three being stale source-assertion tests rather than regressions:
`perf/qt-psi-graduated-reclaim` (2), `feat/qt-native-macos-app` (1).

Filing-order dependencies recorded in the drafts: the four platform wrappers and
both reclaim branches stack on `feat/qt-native-linux-app`;
`perf/gc-rendertail-instrumentation` must precede `perf/rendertail-raf-throttle`
so the counter exists to demonstrate the throttle; `feat/memory-qdrant-nomic` is
marked **HOLD** behind #172. Two are covered under a different filename
(`fix/gguf-quality-scored` -> `feat-gguf-discovery.md`,
`fix/test-temp-db-leak` -> `fix-test-temp-file-leak.md`).

**Two defects found by this inventory and fixed:**

* `fix/longcat-tool-parsing` was **contaminated**. Commit `3140c28f` (2026-08-03,
  the ReDoS rework) swept `src/memory.py`, `src/memory_ranking.py`,
  `src/memory_supersede.py` and their tests into the branch via a blanket add.
  Filing it would have shipped the whole memory feature to upstream under a
  security-fix title. Rewritten as `c06406fe`: 4 files, all LongCat, 16 passed.
  Contaminated version preserved at `refs/salvage/longcat-contaminated`.
* `_fix` — a stray local-only branch, a duplicate of the contaminated LongCat
  file set, created the same day. Deleted.

A scan of the other 89 rebased branches for the same leakage found none.
`feat/logging` touches `src/chroma_client.py` legitimately (it instruments
network I/O paths).

**Method:** `git log --no-merges -p | git patch-id --stable` per side, two
processes. Re-run after every ingest; the naive per-commit form would be ~95,000
subprocesses on this repo. This audit is step 3 of
`docs/fork/post-ingest-checklist.md`, which carries all nine post-merge checks.

**PR drafts:** #172, #173, #174, #175, #176, #182 and #184 written. #174, #182 and #184 also have upstream issue drafts (`docs/fork/upstream/issue-drafts/`).

**Neither #182 nor #184 is filable as written.** A four-lens adversarial review on
2026-08-04 falsified load-bearing claims in both; see #186, #187 and #188. Do not file
either until those are closed.

**Do not file #172 from an old checkout.** The branch gained two commits after the
first cut: `b4f546bd` wires the three remaining recall paths (the module docstring
claimed all four and the branch delivered one), and `b8730071` corrects the
lexical-term benchmark to the current record. The superseded number (4-1,
p=0.375) reads as a weak result; the actual one is 16-3, p = 0.0044.

Full analysis: `docs/fork/upstream-review-20260803.md`.

---

## ⚠ 2026-07-07: rebase state after the 320-commit upstream ingest

`upstream-mirror` advanced to `c67deaa6` (`#5283`), including a module-extraction
refactor. **All staging branches were rebased onto current `upstream-mirror`:
54 clean, 19 conflict** (backed up at `backup/prerebase__*`). The 19 conflicts
need the same resolutions applied in the develop merge (recipes in the branch's
row and in scratch `SYNC_REPORT.md`). **Verify each branch's tests before filing:
a clean rebase is not a correctness guarantee** (spot-checked 7 candidates green /
212 tests; one brittle static test fails on the *superseded* `renderer-memory-reclaim`).

**Superseded by upstream; do not file:** `fix/agent-context-budget-discovery`
(#54) and the #57 lazy-probe research -> upstream **#4886/#4909**. The fork's
`?limit=400` history pagination is superseded by the maintainer's history pager
(direct commit **`45ee5a71`**, NOT #5090, #5090 is only a route-subpackage
refactor; verified via `gh` 2026-07-07). **CAVEAT: that upstream pager is INERT**:
a legacy `/api/history/{sid}` route shadows the paginated endpoint, so it never
paginates (see recon §8; fix staged as #125 on `fix/history-route-shadow`, a clean
single-commit `upstream-mirror` branch). The
fork's `fix/chat-history-server-paging` (merged to develop `6fac912d`) is *also*
built on this broken endpoint; **CONFIRMED inert on develop 2026-07-07**: develop
carries the identical collision (legacy `get_history` present; `session_routes`
registered before `history_routes`), and `_fetchOlderFromServer` calls
`_historyUrl(sid, {limit, offset})` -> the shadow -> full history in one fetch. Its
"150/150 reachable" test passes trivially (all returned at once, not paged).
**Action (DONE 2026-07-07):** route-shadowing fix cherry-picked to develop
(`268d713c`). Verifying it end-to-end surfaced a **severe pre-existing develop bug**:
`sessions.js._mapHistoryMessages` (added by server-paging `90b0ebba`) called
`markdownModule.renderContent` without importing `markdownModule` -> `ReferenceError`
on every session load -> **chat history rendered empty** (error swallowed by
selectSession's catch; missed by static/mock tests). Fixed by adding the import
(`a34ae5a0`) + a real-browser regression test (`dffed66b`, verified to fail without
the fix). After both fixes, verified end-to-end: history renders, scroll-up pages to
the oldest message, DOM stays bounded. The **eviction graft (formerly commit 2 on
`fix/chat-history-dom-eviction`) was dropped**, it hooked the upstream `_installHistoryPager`,
dead code on develop (develop's active pager is the fork MessageWindow, which has its own
eviction), and #2's rewrite carries its own eviction. **`fix/chat-history-dom-eviction` deleted
2026-07-22**: its route-shadow fix was recut alone as `fix/history-route-shadow` (#125); its
eviction graft was superseded and discarded.

`fix/untrusted-tool-result-header` (#48) **rebuilt** as one clean commit on current
`upstream-mirror`, byte-identical to develop; PR draft corrected to the shipped header.

Push state resolved 2026-07-26: develop, integration, and the rebased staging
branches are all on origin. A sweep found three staged branches that had never
been pushed (`fix/cookbook-hf-gguf-repo-nameerror`, `fix/history-route-shadow`,
`fix/sqlalchemy-orm-declarative-import`, each a single clean commit off
`upstream-mirror`, each already cherry-picked to develop); pushed same day.

---

## Branch -> Issue Map

| Branch | Issue | Type | Status |
|--------|-------|------|--------|
| `feat/memory-qdrant-nomic` | [#161](https://github.com/jdmanring/odysseus/issues/161) | Feature | **Single clean commit off `upstream-mirror`; full suite green on branch (4687 passed, 0 failed).** Full memory overhaul: nomic embeddings (256-dim Matryoshka + asymmetric `search_query:`/`search_document:` prefixes) with a llama.cpp GGUF fallback where onnxruntime has no binding (FreeBSD), and the ChromaDB->Qdrant store swap via `src/vector_client.py`, a Chroma-shaped adapter (distance = 1 − score; string-ID -> UUIDv5; `where=` equality filters). Model-change detection kept via a fingerprint sidecar. Tests: `test_vector_client.py` (17, against qdrant-client's in-memory engine) + `test_memory_qdrant_integration.py` (3, real stack). Validated host (fastembed) + FreeBSD (llama.cpp). **Stacks on `feat/logging`**: declares `structlog`, whose migration that branch owns, file/rebase `feat/logging` first, or fold. Still pending: app-managed Qdrant binary lifecycle + installer wiring. Doc: `docs/dev/memory-architecture.md`. **Adapter completeness ([#166](https://github.com/jdmanring/odysseus/issues/166)):** the adapter shipped without `_Collection.update()` while `VectorRAG.rename_owner` calls it inside a bare `except` -> a username rename silently orphaned all of that user's personal RAG docs. Added `update()` (Qdrant `set_payload` merge) + `tests/test_vector_client_update.py`, **folded into the migration commit (squashed to `13e17b87`, still a single clean commit off `upstream-mirror`)**; cherry-picked to develop (`bce4a072`). Branch pushed to origin. |
| `fix/agent-tool-budget` | [#10](https://github.com/jdmanring/odysseus/issues/10) | Bug | Ready to file: added `tests/test_agent_tool_budget.py` (5 tests: zero-bypass guard present, 0=unlimited at any call count, default=20, positive limit triggers at threshold). See pr-drafts/ |
| `fix/pytest-timeout-dependency` | [#6](https://github.com/jdmanring/odysseus/issues/6) | Bug | Ready to file; see pr-drafts/ |
| `fix/searxng-json-docs` | [#8](https://github.com/jdmanring/odysseus/issues/8) | Bug/Docs | Ready to file: see pr-drafts/ |
| `fix/basicsr-python314-compat` | [#9](https://github.com/jdmanring/odysseus/issues/9) | Bug | Ready to file: single squashed commit. PR #3741 covers the Serve panel only; this PR also covers the Dependencies tab (`shell_routes.py`) and adds inline POSIX abort. File upstream issue first (draft in issue-drafts/). See pr-drafts/ |
| `fix/streamingtts-scope` | [#11](https://github.com/jdmanring/odysseus/issues/11) | Bug | **FILE IT — the supersession expired.** Upstream PR #2418 (same hoist fix) is **CLOSED, not merged** (verified 2026-08-03), and `upstream-mirror` still carries `const streamingTTS` inside the try block. Our fix is again the only one. The earlier "superseded, do not file" verdict was correct while #2418 was open and became wrong when it closed. Delete branch once #2418 merges into upstream-mirror. |
| `refactor/assets-move` | [#19](https://github.com/jdmanring/odysseus/issues/19) | Refactor | Ready to file; see pr-drafts/ |
| `fix/tool-result-role` | [#4](https://github.com/jdmanring/odysseus/issues/4) | Bug | **Do not file: superseded by upstream #1629, branch deleted (2026-06-18).** #1629 wraps tool results via `untrusted_context_message()` as guarded `role: user` messages, so they stay inline and never collapse into `system_parts` (verified on develop). The fork's code path is dead. Draft marked SUPERSEDED. |
| `fix/dom-oom-virtualization` | [#2](https://github.com/jdmanring/odysseus/issues/2) | Bug | **More-complete alternative to open upstream PR #4661, with an independent architecture** authored nine days before #4661 opened (plan Part 1.2 is the settled provenance framing, use it verbatim, everywhere). Ours adds bidirectional scroll-up and releases StreamRenderer/IntersectionObserver/hljs-defer refs; #4661 is smaller. Offer on merits, acknowledging #4661 as parallel work on the same problem. Branch contamination (PR-draft .md) removed. **Plan: `docs/fork/plans/dom-oom-virtualization-upstream-plan.md`, its Part 4.5 is mandatory: the server-paging fold must carry the #129 chIdx-retag fix (`ac18291a`) and its regression test, or the filed PR ships a measured unbounded-DOM defect. Fork #129 stays open until this PR is filed.** **Wipe-guard completeness ([#164](https://github.com/jdmanring/odysseus/issues/164)):** #2's `reset()`-before-wipe invariant was missing at four clear paths (`createDirectChat`/New Chat, `_cmdSessionClear`/`/clear`, `_arcPeekOpen`/archived-view, group-chat start), a restored session left `_serverTotal` alive so the header showed a stale "New Chat · N msgs". A repo-wide sweep of every `getElementById('chat-history')` acquisition confirmed the set. Fixed on the branch (`e82945fe`), cherry-picked to develop, with source-assertion guard `tests/test_chat_history_reset_before_wipe_js.py`. Folds into #2: no separate PR. |
| `fix/history-route-shadow` | [#125](https://github.com/jdmanring/odysseus/issues/125) | Bug | **Standalone route-shadow fix**, recut clean from `upstream-mirror` 2026-07-22 (single commit `2dfcdb32`, 0 fork commits): removes the legacy `/api/history/{sid}` route that shadows the maintainer's paginated endpoint, making upstream's own pager inert. Fixes an upstream-shipped bug independent of the #2 rewrite; #2's paging depends on it. Replaces the deleted `fix/chat-history-dom-eviction` (whose eviction graft was superseded by #2's own eviction). |
| `fix/truncate-fork-by-msg-id` | [#169](https://github.com/jdmanring/odysseus/issues/169) | Bug | **Single clean commit `c3ec7cf7` off `upstream-mirror`; cherry-picked to develop (`d0b145e0`).** Edit/regenerate/fork derived the server `keep_count` from `indexOf('.msg')` (DOM position) while the server applies it as an absolute DB index, wrong truncation/fork point under pagination, synthetic "Continue…" turns, and multi-bubble replies (silent message loss). Fix addresses messages by DB id: precondition stamps `_db_id` into the paginated `/history` payload (also repairs delete-by-id on scrolled-back history), `SessionManager.truncate_from_message` + `/truncate from_msg_id` + `/fork through_msg_id` resolve by id within each store, client sends `dataset.dbId`, `keep_count` kept as fallback. Pre-existing in both branches; #2 reduces its blast radius. `keep_count` retained as fallback (the `/truncate N` + `/fork` slash commands and the `manage_session` AI tool are legitimately count-based). Tests `tests/test_truncate_fork_by_msg_id.py` (truncate/fork-by-id over synthetic-turn history, `_db_id` precondition via real endpoint, client guard); full `-k "history or truncate or fork or session"` suite green (436). **Depends on #125** (`fix/history-route-shadow`) for the paginated endpoint to be live: file #125 first. See pr-drafts/fix-truncate-fork-by-msg-id.md. |
| `feat/aria2c-downloader` | [#12](https://github.com/jdmanring/odysseus/issues/12) + [#23](https://github.com/jdmanring/odysseus/issues/23) | Feature | Verified (2026-06-12): pause/resume (single+multi-file), split-file size, menu toggle, clear-finished, zombie detection, resume spinner, cancel mid-download. Windows buffering fix implemented (untested, needs Windows machine). aria2c is now the default (`use_aria2c: bool = True` in schema); hf-download is the pre-flight fallback when aria2c binary unavailable. Added `tests/test_aria2c_circuit.py` with `@pytest.mark.slow` on network classes + 4 static contract tests. **File before `fix/gguf-quality-scored`** (introduces `HfUrlResolver` base class). See pr-drafts/ |
| `feat/catppuccin-theme` | [#30](https://github.com/jdmanring/odysseus/issues/30) | Feature | Ready to file: see pr-drafts/feat-catppuccin-theme.md |
| `feat/ai-documentation-system` | [#18](https://github.com/jdmanring/odysseus/issues/18) | Docs | Ready to file; see pr-drafts/ |
| `feat/qt-native-linux-app` | [#14](https://github.com/jdmanring/odysseus/issues/14) | Feature | **File-ready (single squashed commit); pending only the standard issue-first + screenshot at filing.** Carries the full Qt-wrapper memory stack (#106 forcible-purge + RSS-ceiling, #112 host telemetry, #116 low-resource profile, #120 graduated PSI / `qt_psi.py`), folded 2026-06-26 because `qt_wrapper.py` is a *new* file (ships memory-managed, not patched after). **Gate 1 (history) RESOLVED:** squashed the 44-commit branch to one coherent commit (`feat(linux): native Linux desktop app … with renderer memory management`) on the `upstream-mirror` fork point; verified the squash changed only history (`git diff backup/feat-qt-pre-squash feat/qt-native-linux-app` is *only* the intended `docs/fork/` drops). The squash also dropped 8 fork-only files (debug screenshots + an unrelated deprecated draft) that had contaminated the branch. Voice pass applied (no em-dashes in code, log lines, tests, or the PR draft). **Gate 2 (verification) RESOLVED:** the `CRITICAL -> _purge_renderer('psi-critical')` dispatch is now unit-tested deterministically via `qt_psi.dispatch_psi_action` (a headless harness and a cgroup-capped stress-ng cannot reach real CRITICAL), and the live app proves the integration (drain runs; `_purge_renderer` purges; `[PSI]` heartbeats with real `rss_mb`). Backups: `backup/feat-qt-native-linux-app-prefold` (pre-fold), `backup/feat-qt-pre-squash` (pre-squash). At file time, rebase onto then-current `upstream-mirror` per the standing requirement. See pr-drafts/feat-qt-native-linux-app.md |
| `fix/gpu-compositor-flicker` | [#32](https://github.com/jdmanring/odysseus/issues/32) | Bug | Ready to file: see pr-drafts/fix-gpu-compositor-flicker.md |
| `fix/css-render-perf` | [#33](https://github.com/jdmanring/odysseus/issues/33) | Perf | Ready to file; see pr-drafts/fix-css-render-perf.md |
| `fix/hf-token-env-fallback` | [#34](https://github.com/jdmanring/odysseus/issues/34) | Bug | Superseded: upstream landed same fix in #3459 (synced 2026-06-12). Draft moved to `deprecated/`. Do not file. |
| `feat/gh-cli-detection` | [#5](https://github.com/jdmanring/odysseus/issues/5) | Feature | Ready to file: module-level cache added (subprocess called once per server lifetime); 12 tests (11 behavioral + 1 cache test). See pr-drafts/feat-gh-cli-detection.md |
| `fix/gguf-quality-scored` | [#24](https://github.com/jdmanring/odysseus/issues/24) + [#29](https://github.com/jdmanring/odysseus/issues/29) | Feature | Ready to file after `feat/aria2c-downloader` (extends `HfUrlResolver`, gguf discovery methods). Added `tests/test_gguf_scoring.py` with 20 pure-function tests (no network). See pr-drafts/feat-gguf-discovery.md |
| `fix/tool-code-pycall-parsing` | [#35](https://github.com/jdmanring/odysseus/issues/35) | Bug | Ready to file: see pr-drafts/fix-tool-code-pycall-parsing.md |
| `fix/longcat-tool-parsing` | [#38](https://github.com/jdmanring/odysseus/issues/38) | Bug | Ready to file: added `tests/test_longcat_tool_parsing.py` (13 tests, covers both Variant A/B, unknown-name pass-through behavior documented). See pr-drafts/fix-longcat-tool-parsing.md |
| `fix/google-compat-toolcalls` | [#39](https://github.com/jdmanring/odysseus/issues/39) | Bug | **Do not file: premise disproved, branch deleted (2026-06-18).** A live API test showed Google's compat endpoint sends snake_case `tool_calls` per spec, not camelCase; the fix chased a non-existent bug. The real related quirk (`finish_reason: stop`) does not affect Odysseus (tracked #52). See active-work.md; draft retained for history only. |
| `feat/logging` | [#31](https://github.com/jdmanring/odysseus/issues/31) | Feature | Ready to file: infrastructure and callsites combined in one PR. See pr-drafts/feat-logging.md |
| `fix/workspace-shell-access` | [#47](https://github.com/jdmanring/odysseus/issues/47) | Bug | **Folded into develop; standalone branch deleted.** The web_search/web_fetch workspace behavior is on develop and `tests/test_workspace_web_search_tools.py` passes there. To file upstream, recreate a clean branch from `upstream-mirror`. Entry was stale. |
| `fix/untrusted-tool-result-header` | [#48](https://github.com/jdmanring/odysseus/issues/48) | Bug | Ready to file: single clean commit. Fixes false-positive refusals introduced by upstream #1629 (2026-06-16). File upstream issue first. See pr-drafts/fix-untrusted-tool-result-header.md |
| `feat/unify-llamacpp-embeddings` | #TBD (add to `docs/fork/issues/`) | Feature/Refactor | **No such branch exists; entry was stale.** Corrected 2026-08-04 after an audit found the row describing a live draft that resolves to no ref. The work is on develop as `968e9b98` (originally committed as `ba1aaea0`, which is now reflog-only and unreachable; identical patch-id `c03e2c97`, so nothing was lost). Retires the onnxruntime/fastembed backend; llama.cpp (GGUF Q8_0) is the default embedder on all platforms, fastembed opt-in. **Still not ready to file:** needs multi-platform install verification (wheel-index resolution) + a fork issue, and to file upstream a clean branch must be recreated from `upstream-mirror`. See pr-drafts/feat-unify-llamacpp-embeddings.md |
| `fix/api-token-utcnow-deprecated` | [#51](https://github.com/jdmanring/odysseus/issues/51) | Bug | Ready to file: single clean commit, 2 lines changed. Follow-up to upstream 790ef81b (missed instance). File upstream issue first. See pr-drafts/fix-api-token-utcnow-deprecated.md |
| `fix/sqlalchemy-orm-declarative-import` | [#163](https://github.com/jdmanring/odysseus/issues/163) | Bug | Ready to file: single clean commit off `upstream-mirror`, cherry-picked to develop (`30819e02`, `-x`). `core/database.py` imported `declarative_base`/`declared_attr` from the deprecated `sqlalchemy.ext.declarative` (MovedIn20Warning on 2.0); folded into the existing `sqlalchemy.orm` import. Regression guard `tests/test_database_declarative_import.py`; verified warning gone via `-W error`. Sibling to #51. File upstream issue first. See pr-drafts/fix-sqlalchemy-orm-declarative-import.md |
| `fix/chat-auto-scroll-threshold` | [#49](https://github.com/jdmanring/odysseus/issues/49) | Bug | Ready to file: single clean commit. Adaptive threshold replaces rigid 300px guard in _smoothScrollStep(). File upstream issue first. See pr-drafts/fix-chat-auto-scroll-threshold.md |
| `feat/thinking-overlay` | [#133](https://github.com/jdmanring/odysseus/issues/133) | Enhancement | Ready to file: single clean commit (`9d959850`) from `upstream-mirror`; cherry-picked to develop (`163cbc52`, `-x`). Thinking indicator becomes a zero-footprint sticky overlay (height:0 sticky anchor + absolute bubble): document bottom never moves on show/replace/remove (measured: scrollHeight and pinned bottom-distance identical), indicator stays visible when scrolled up, role=status for AT, no compositor-layer properties. 7 static guards. File upstream issue first. See pr-drafts/feat-thinking-overlay.md |

### Index completion: commit-verified branch->issue map (2026-07-22)

The 56 clean staged branches below were absent from the map above; each is mapped to its
issue with commit-level evidence (verification pass 2026-07-22). Terser than the curated
entries above by design: these are the coverage backfill. See FLAGS note after the table.

| Branch | Issue | Type | Status |
|--------|-------|------|--------|
| `bench/chat-history-virtualization` | [#128](https://github.com/jdmanring/odysseus/issues/128) | Test/Bench | OPEN: Reproducible virtualization benchmark (four arms). Dev bench for #2; not a standalone PR. |
| `feat/asset-cache-busters` | [#154](https://github.com/jdmanring/odysseus/issues/154) | Feature | OPEN: Content-hash ?v= cache-busters at serve time. |
| `feat/chat-column-width-pref` | [#144](https://github.com/jdmanring/odysseus/issues/144) | Feature | OPEN: Chat column width preference setting. |
| `feat/longcat-provider` | [#58](https://github.com/jdmanring/odysseus/issues/58) | Feature | OPEN: LongCat (Meituan) provider integration. Also folds #61 (32K truncation / stream_options), no separate branch. |
| `feat/nvidia-nim-support` | [#56](https://github.com/jdmanring/odysseus/issues/56) | Feature | OPEN: NIM catalog context windows + curated fixes. Reopened 2026-07-22; was prematurely closed (COMPLETED); awaiting upstream PR. |
| `feat/qt-native-freebsd-app` | [#45](https://github.com/jdmanring/odysseus/issues/45) | Feature | OPEN: build-freebsd-app.sh + install dispatcher. Reopened 2026-07-22; was prematurely closed (COMPLETED); awaiting upstream PR. |
| `feat/qt-native-macos-app` | [#43](https://github.com/jdmanring/odysseus/issues/43) | Feature | OPEN: mac_wrapper.py rebuilt to qt_wrapper parity. |
| `feat/qt-native-openbsd-app` | [#46](https://github.com/jdmanring/odysseus/issues/46) | Feature | OPEN: build-openbsd-app.sh. |
| `feat/qt-native-windows-app` | [#44](https://github.com/jdmanring/odysseus/issues/44) | Feature | OPEN: windows_wrapper.py Qt WebEngine wrapper. |
| `feat/skill-quality-signals` | [#87](https://github.com/jdmanring/odysseus/issues/87) | Feature | OPEN: BM25 hybrid retrieval + composite skill health score. |
| `fix/api-hosts-provider-gaps` | [#62](https://github.com/jdmanring/odysseus/issues/62) | Bug | OPEN: Expand _API_HOSTS for provider secondary domains/proxies. |
| `fix/brain-panel-oom` | [#108](https://github.com/jdmanring/odysseus/issues/108) | Bug | OPEN: Brain synapse-sweep made hover-triggered, not perpetual. |
| `fix/chat-stick-to-bottom` | [#145](https://github.com/jdmanring/odysseus/issues/145) | Bug | OPEN: Direction-based stick-to-bottom; release on one wheel notch. |
| `fix/cookbook-hf-gguf-repo-nameerror` | [#135](https://github.com/jdmanring/odysseus/issues/135) | Bug | OPEN: NameError in `hf_gguf_files` error path (undefined `repo`). Renamed 2026-07-22 from the misleading `fix/chat-stream-web-intent-nameerror` (that name belonged to #134, which is a different, now-closed bug). |
| `fix/continue-btn-weakref` | [#78](https://github.com/jdmanring/odysseus/issues/78) | Bug | OPEN: WeakRef for continue-button holder captures. Reopened 2026-07-22; was prematurely closed (COMPLETED); awaiting upstream PR. |
| `fix/css-contain-paint-transparent-rendering` | [#93](https://github.com/jdmanring/odysseus/issues/93) | Bug | OPEN: contain:layout on sidebar and chat-history. |
| `fix/declare-magic-docx-test-deps` | [#136](https://github.com/jdmanring/odysseus/issues/136) | Bug | OPEN: Declare python-magic (optional) + python-docx (test-only). |
| `fix/dom-oom-streaming-throttle` | [#64](https://github.com/jdmanring/odysseus/issues/64) | Perf | OPEN: Thinking textContent / rAF throttle / teardown. Reopened 2026-07-22; was prematurely closed (COMPLETED); awaiting upstream PR. |
| `fix/editor-empty-save-guard` | [#101](https://github.com/jdmanring/odysseus/issues/101) | Bug | OPEN: Guard editor save against 0-byte output. |
| `fix/editor-redo-shortcut` | [#100](https://github.com/jdmanring/odysseus/issues/100) | Bug | OPEN: Ctrl+Shift+Z redo accepts uppercase 'Z'. |
| `fix/hwfit-scan-honesty` | [#149](https://github.com/jdmanring/odysseus/issues/149) + [#150](https://github.com/jdmanring/odysseus/issues/150) + [#151](https://github.com/jdmanring/odysseus/issues/151) | Bug | OPEN: **Multi-issue branch**, one commit each: #151 sort-refetch, #150 servability gate, #149 fabricated Q4_K_M identity. Matches issue-tracker.md. |
| `fix/memory-list-scroll-oom` | [#88](https://github.com/jdmanring/odysseus/issues/88) | Bug | OPEN: Override transition:all in #memory-list. Reopened 2026-07-22; was prematurely closed (COMPLETED); awaiting upstream PR. |
| `fix/memory-panel-listener-leak` | [#89](https://github.com/jdmanring/odysseus/issues/89) | Bug | OPEN: Eliminate listener accumulation / raster-tile retention. Reopened 2026-07-22; was prematurely closed (COMPLETED); awaiting upstream PR. |
| `fix/modal-zpromote-reduced-motion-oom` | [#156](https://github.com/jdmanring/odysseus/issues/156) | Bug | OPEN: Modal z-promote observer OOM under reduced motion. |
| `fix/model-downloaded-detection` | [#121](https://github.com/jdmanring/odysseus/issues/121) | Bug | OPEN: One canonical 'is model downloaded?' predicate. |
| `fix/nvidia-native-tool-calling` | [#60](https://github.com/jdmanring/odysseus/issues/60) | Bug | OPEN: NIM models receive native tool schemas. |
| `fix/provider-logo-ordering` | [#59](https://github.com/jdmanring/odysseus/issues/59) | Bug | OPEN: Gemini ordering bug + Pollinations. (Overlaps #59/#122 territory with #56 branch.) |
| `fix/provider-picker-alpha-sort` | [#122](https://github.com/jdmanring/odysseus/issues/122) | Bug | OPEN: Sort Add API Models picker alphabetically. |
| `fix/qtwebengine-oilpan-gc` | [#67](https://github.com/jdmanring/odysseus/issues/67) | Bug | OPEN: Deferred async GC for Oilpan nodes. Shares base GC commits with #80 (folds #69). |
| `fix/renderer-hang-watchdog` | [#137](https://github.com/jdmanring/odysseus/issues/137) | Bug | OPEN: Renderer-hang watchdog for wedged main thread. |
| `fix/settings-shortcut-resurrection` | [#143](https://github.com/jdmanring/odysseus/issues/143) | Bug | OPEN: Settings keybind opens Settings, never a remembered tool window. |
| `fix/skill-agent-prompt-language` | [#85](https://github.com/jdmanring/odysseus/issues/85) | Bug | OPEN: Reframe skill prompts as advisory. Reopened 2026-07-22; was prematurely closed (COMPLETED); awaiting upstream PR. |
| `fix/skill-extraction-threshold` | [#84](https://github.com/jdmanring/odysseus/issues/84) | Bug | OPEN: Raise extraction gate (rounds>=2 AND tools>=3). Reopened 2026-07-22; was prematurely closed (COMPLETED); awaiting upstream PR. |
| `fix/skill-lifecycle-correctness` | [#86](https://github.com/jdmanring/odysseus/issues/86) | Bug | OPEN: Correct auto_approve_skills semantics across pipeline. |
| `fix/spinner-orphan-leak` | [#107](https://github.com/jdmanring/odysseus/issues/107) | Bug | OPEN: Stop orphaned/hidden spinner animation loops. |
| `fix/stream-429-backoff` | [#55](https://github.com/jdmanring/odysseus/issues/55) | Bug | OPEN: Respect Retry-After on 429 (streaming + async). Reopened 2026-07-22; was prematurely closed (COMPLETED); awaiting upstream PR. |
| `fix/tasks-clock-repaint` | [#110](https://github.com/jdmanring/odysseus/issues/110) | Perf | OPEN: Isolate Tasks clock to its own layer. |
| `fix/theme-reduced-motion` | [#155](https://github.com/jdmanring/odysseus/issues/155) | Bug | OPEN: Honor prefers-reduced-motion for canvas background effects. |
| `fix/tool-bubble-timer-leak` | [#73](https://github.com/jdmanring/odysseus/issues/73) | Bug | OPEN: Stop tool-bubble timers before _isBg skip. Reopened 2026-07-22; was prematurely closed (COMPLETED); awaiting upstream PR. |
| `fix/vllm-desktop-serve-resilience` | [#153](https://github.com/jdmanring/odysseus/issues/153) | Bug | OPEN: vLLM launches survive missing CUDA toolkit. |
| `perf/agent-finalize-in-place` | [#74](https://github.com/jdmanring/odysseus/issues/74) | Perf | OPEN: Finalize live-reply renderer in-place. Reopened 2026-07-22; was prematurely closed (COMPLETED); awaiting upstream PR. |
| `perf/agent-gc-catchup` | [#80](https://github.com/jdmanring/odysseus/issues/80) | Perf | OPEN: Missed-GC catch-up + idle reclaim. Shares GC base with #67. Reopened 2026-07-22 (was prematurely closed). |
| `perf/editor-undo-compress` | [#99](https://github.com/jdmanring/odysseus/issues/99) | Perf | OPEN: Compress aged-out undo snapshots (issue says PNG; same intent). |
| `perf/gc-micro-improvements` | [#82](https://github.com/jdmanring/odysseus/issues/82) | Perf | OPEN: squashOutsideCode fast path for plain text. Reopened 2026-07-22; was prematurely closed (COMPLETED); awaiting upstream PR. |
| `perf/gc-rendertail-instrumentation` | [#68](https://github.com/jdmanring/odysseus/issues/68) | Perf | OPEN: renderTail call counter. |
| `perf/hljs-deferred-highlight` | [#66](https://github.com/jdmanring/odysseus/issues/66) | Perf | OPEN: Defer hljs highlighting for off-screen code blocks. |
| `perf/image-lazy-decode` | [#98](https://github.com/jdmanring/odysseus/issues/98) | Perf | OPEN: Lazy-decode off-screen pages/gallery thumbs. |
| `perf/rendertail-raf-throttle` | [#70](https://github.com/jdmanring/odysseus/issues/70) | Perf | OPEN: Throttle live tail renders to one/frame. Reopened 2026-07-22; was prematurely closed (COMPLETED); awaiting upstream PR. |
| `perf/rendertail-text-only-path` | [#75](https://github.com/jdmanring/odysseus/issues/75) | Perf | OPEN: Skip renderTail parse for plain-text appends. Reopened 2026-07-22: was prematurely closed (COMPLETED); awaiting upstream PR. **Fixes ([#168](https://github.com/jdmanring/odysseus/issues/168)):** the fast-path guard omitted `~`, so streamed `~~strikethrough~~` rendered literal until freeze; and a debug `console.log` shipped, firing on every finalized message (`finalize()` *is* called in prod). Both fixed + dev instrumentation removed (`cb5a28a7`), cherry-picked to develop (`dec9a388`), guard `tests/test_streaming_textpath_js.py`. |
| `perf/rewrite-streaming-renderer` | [#79](https://github.com/jdmanring/odysseus/issues/79) | Perf | OPEN: Stream rewrite path through streamingRenderer (O(n^2) rewriteWith). |
| `perf/round-finalize-inplace` | [#77](https://github.com/jdmanring/odysseus/issues/77) | Perf | OPEN: Finalize agent round content in-place. |
| `perf/smooth-typing` | [#81](https://github.com/jdmanring/odysseus/issues/81) | Perf | OPEN: rAF-coalesced autoResize (typing lag). Reopened 2026-07-22: was prematurely closed (COMPLETED); awaiting upstream PR. |
| `perf/streaming-final-render` | [#71](https://github.com/jdmanring/odysseus/issues/71) | Perf | OPEN: Skip final innerHTML re-render for plain responses. |
| `perf/tool-bubble-inplace` | [#72](https://github.com/jdmanring/odysseus/issues/72) | Perf | OPEN: Patch tool bubble state in-place at completion. |

**NOT fork contributions, upstream comparison references (do not stage, do not index as ours):**
`test/upstream-pr-4366` and `test/upstream-pr-4661` are local copies of *upstream's own* open PRs
(commits authored by `sept` and `holden093`), kept on a mirror base to evaluate the rival work.
Both upstream PRs are **OPEN / unmerged** as of 2026-07-22 and are not in `upstream-mirror`.
`test/upstream-pr-4661` is the browser-OOM PR that our #2 (`fix/dom-oom-virtualization`) supersedes
as the more-complete alternative. Retire both once the competing fork PRs (#2 and the #47 agent-tool
work) are filed and decided. (The contaminated `test/pr-4366` / `test/pr-4661` whole-fork snapshots
are separate debris, delete outright.)

**FLAGS from the verification pass (2026-07-22):**
- **#134 CLOSED 2026-07-22, superseded upstream, verified.** The branch formerly named
  `fix/chat-stream-web-intent-nameerror` (now `fix/cookbook-hf-gguf-repo-nameerror`)
  was *named* for #134 but its commit actually fixes #135 (`hf_gguf_files` undefined `repo`). #134's
  NameError was already fixed by upstream #5290 (`54353492`, restores the `_explicit_web_intent`
  definition), confirmed present in `upstream-mirror`'s `routes/chat_routes.py` (def line 882, sole
  read line 885; the dangling reads are gone). No fork branch needed; issue closed with evidence.
- **17 branches map to CLOSED issues** (see CLOSED rows above). Per the fork rule, an upstream-candidate issue stays OPEN until its PR is filed, so a CLOSED issue here means the PR was filed, the issue was closed prematurely, or the branch is superseded. Each needs a one-line disposition; none has been filed upstream (see top of file: "Nothing pushed yet"), which points at premature closings to re-open or branches to retire.
- **Folded issues without their own branch:** #61 rides in `feat/longcat-provider` (#58); #69 rides in `fix/qtwebengine-oilpan-gc` (#67) / `perf/agent-gc-catchup` (#80). Intentional folds, recorded here so the issues aren't presumed orphaned.

## Process-stack perf candidates (audit section E, 2026-06-25)

Three fork issues filed from `docs/fork/perf-audit-2026-06.md`. Their **branch origin
differs by whether the touched files exist on `upstream-mirror`**: getting this wrong
contaminates the branch:

| Fork issue | Touches | Origin / home | Independent? | Maps upstream to |
|---|---|---|---|---|
| [#111](https://github.com/jdmanring/odysseus/issues/111) lazy-connect cold MCP | `src/builtin_mcp.py`, `src/mcp_manager.py` (both on `upstream-mirror`) | **`perf/mcp-lazy-connect`** (cut from `upstream-mirror`; implemented, cherry-picked to develop; draft issue+PR staged; research in `mcp-lazy-connect-research.md`) | **Yes** | #2140, #3824; ROADMAP email-perf. #4812 reconciled (complementary; file after #4812, route eager branch through its `_spawn_bg`, see research doc) |
| [#112](https://github.com/jdmanring/odysseus/issues/112) host VmRSS telemetry | `qt_wrapper.py` (**not** on `upstream-mirror`) | **folded into `feat/qt-native-linux-app` (#14)** with the rest of the memory stack, 2026-06-26 | No: **part of #14** | ships inside the #14 PR |
| [#113](https://github.com/jdmanring/odysseus/issues/113) `--no-access-log` | `qt_wrapper.py` / `mac_wrapper.py` / `windows_wrapper.py` (**not** on `upstream-mirror`) | **DONE** on each `feat/qt-native-{linux,macos,windows}-app` branch; cherry-picked to develop (guard test on develop) | No: **rides each platform PR** | folds into #14 (linux) + macos/windows PRs. Real fix is `--no-access-log` (uvicorn default is ON) |

### Idle-quiescence candidates (audit C3 / #117, 2026-06-25)

| Fork issue | Branch | Touches | Status |
|--------|--------|---------|--------|
| [#117](https://github.com/jdmanring/odysseus/issues/117) (notes instance) | `fix/notes-quick-idle-quiescence` | `static/js/ui.js`, `static/style.css` | **DONE**: from `upstream-mirror`, cherry-picked to develop; draft issue+PR staged; adds reusable `html.app-blurred` primitive. Independent. |
| [#115](https://github.com/jdmanring/odysseus/issues/115) | `fix/research-orbit-quiescence` | `static/js/research/panel.js`, `static/style.css` | **DONE: orbit ring REMOVED** (not just optimized): a compositor version needed a ~32 MB GPU layer for decoration, and VRAM is the model's context. From `upstream-mirror`, cherry-picked to develop; draft issue+PR staged. Independent. |
| [#118](https://github.com/jdmanring/odysseus/issues/118) (audit D1+D2) | `fix/timer-visibility-gating` | `modalManager.js`, `emailInbox.js`, `tasks.js` | **DONE**: visibility-gate background timers; from `upstream-mirror`, cherry-picked to develop; draft issue+PR staged. Independent. |
| [#119](https://github.com/jdmanring/odysseus/issues/119) (audit D3) | `fix/sigcache-lru-bound` | `static/js/document.js` | **DONE**: LRU-bound `_sigCache`; from `upstream-mirror`, cherry-picked to develop; draft issue+PR staged. Independent. |

**✓ Staging gap RESOLVED (2026-06-26): folded into #14.** The memory work
(`perf/renderer-memory-reclaim` = #106 forcible-purge/idle-purge/GC-catchup + #112 host
telemetry + #116 low-resource profile, and `perf/qt-psi-graduated-reclaim` = #120 graduated
PSI / `qt_psi.py`) could not be a standalone `upstream-mirror` PR because `qt_wrapper.py` is
introduced by #14. **Decision: fold all of it into #14**, `qt_wrapper.py` is a *new* file,
so the feature must ship in its correct memory-managed shape rather than be introduced naive
and patched by a follow-up series (which would also ask a reviewer to accept the
simulatePressure no-op that #106's research disproved). 13 commits were cherry-picked onto
`feat/qt-native-linux-app` (clean; backup `backup/feat-qt-native-linux-app-prefold`); the #14
PR draft was rewritten to the shipped design. `develop` already carries all of this work via
its own cherry-picks. The `perf/renderer-memory-reclaim` and `perf/qt-psi-graduated-reclaim`
branches are now **superseded by #14** for upstream purposes (retained as history; safe to
delete once #14 is filed). **#113** keeps its own row: the Linux part is in #14, the
mac/windows parts ride their platform PRs. **Do not file #14 until its upstream fate is
settled** (issue first, per CONTRIBUTING).

## PR Drafts and Issue Drafts

Staged PR descriptions live in `docs/fork/upstream/pr-drafts/`, one file per branch
(named after the branch with `/` -> `-`). Each draft contains the proposed title,
description body, and filing notes. The description is written for upstream
reviewers, it does not assume they have seen our fork's issue tracker.

For branches that require a new upstream issue to be filed first, a pre-written issue
(title + body, ready to paste) lives in `docs/fork/upstream/issue-drafts/<name>.md`.
File the issue on `odysseus-dev/odysseus`, get its number, fill it into
`Fixes #` in the PR draft, then open the PR.

## Filing Procedure

1. File a GitHub issue on `odysseus-dev/odysseus` (from `issue-drafts/<name>.md`)
2. Add the upstream issue number to `Fixes #` in the PR draft
3. Open PR from `<your-fork>:<branch>` -> `odysseus-dev/odysseus:dev`
4. All PRs target `dev`, not `main`

## Fork-Only Work (not going upstream)

| Branch | Issue | Notes |
|--------|-------|-------|
| `feat/upstream-sync-pipeline` | [#15](https://github.com/jdmanring/odysseus/issues/15) | Manages fork/upstream relationship, not applicable upstream |
