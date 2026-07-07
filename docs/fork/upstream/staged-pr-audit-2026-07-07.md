# Staged-PR Deep Audit — 2026-07-07

Maintainer-grade review of every staged upstream-candidate branch (mechanical
hygiene pass + 7 parallel deep code-reviews). Question asked: *were these made as
a senior developer would make them?* Honest answer: **the craft is high and a
large core is genuinely senior-grade, but a real subset would be sent back by a
professional maintainer** — for provenance, commit-message-vs-diff mismatch,
functional bugs, scope creep, and test quality. Details below.

## Mechanical pass (all 75 branches) — clean
- **Zero fork contamination** (no `CLAUDE.md`/`docs/fork/` in any diff).
- **Zero hardcoded paths/usernames/secrets.**
- Most single-commit; multi-commit ones need squashing before filing (qt-macos/windows 14, dom-oom-virtualization 15).

## Blockers — NEEDS-WORK (do not file as-is)
| Branch | Blocker |
|---|---|
| **fix/dom-oom-virtualization** | **Provenance failure.** Per-node teardown in `_evictLive` is adapted-and-extended from upstream **#4661** (the fork's own notes say so) — **zero** attribution in any commit or comment (verified). A maintainer will reject undisclosed borrowed code. Also ~2430 lines / trial-and-error history → split Phase 1/2/3. (Upside: the *only* branch with a real Playwright behavior test.) |
| **feat/aria2c-downloader** | **Remote downloads broken** — runner executes the *server's* local `Path(__file__)/tooling/aria2c_download.py` on the remote host (verified); `--repo {req.repo_id}` **unquoted** (others use `_bash_squote`); Windows `os.kill(pid,0)` *kills* instead of probing; unrelated `disable_hf_transfer` default flip bundled in. Local path + tests are otherwise senior-grade. |
| **feat/nvidia-nim-support** | **Scope creep**: a NIM catalog data change smuggles in a codebase-wide `_lookup_known` ranking-algorithm rewrite (`model_context.py:362`, affects every provider) + endpoint auto-naming for all providers (untested). Speculative/unverifiable model IDs. Split. |
| **fix/basicsr-python314-compat** | **Commit message misrepresents the diff** — advertises a "Python 3.10+ / `collections.abc` patch" that is **entirely absent**; the code only no-ops below 3.13 and patches `get_version()`. Fix the message to 3.13+ or actually add the advertised patch. |
| **fix/css-render-perf** | **Undisclosed counter-productive scope creep** — message says "will-change cleanup," diff *adds* permanent `will-change/translateZ` layers to `.chat-container`/`.chat-input-bar`/`textarea` (violates the VRAM-scarce principle) and ships the `contain:paint`-on-`.sidebar`/`.chat-history` defect that its sibling `fix/css-contain-paint-transparent-rendering` exists to fix. Bundles 5 concerns. |
| **perf/chathistory-gc-improvements** | Bundles the 916-line virtualization **engine** with the "improvements" — split the teardown/leak fixes from the engine. |

## Concerns — real issues, fix before filing
- **fix/skill-extraction-threshold ↔ fix/skill-lifecycle-correctness** — **mutually exclusive**: flip `auto_approve_skills` default in *opposite* directions at the same three sites. At most one can land; pick one semantics.
- **feat/skill-quality-signals** — **IDF-cache staleness bug**: `_idf_cache` computed over the first corpus, applied to later different corpora (per-owner/status subsets) → silently wrong BM25 rankings; not covered by tests.
- **fix/longcat-tool-parsing** — over-broad `except (JSONDecodeError, Exception)` swallows real dispatch bugs; passes unknown tool names through (injection surface) — disagrees with sibling `fix/tool-code-pycall-parsing` which filters via `TOOL_TAGS`. Reconcile.
- **fix/spinner-orphan-leak** — `offsetParent`-based visibility test wrongly kills spinners inside `position:fixed` overlays; also forces per-frame layout. Use `checkVisibility()`/`getClientRects()`.
- **perf/rendertail-text-only-path** — smuggles an undisclosed sync→deferred highlight change into a "text-only path" commit; raw-suffix append can diverge from the markdown parse on bare URLs.
- **fix/chat-stick-to-bottom** — `subtree+characterData` MutationObserver over `#chat-history` fires per token (works against the very perf goals the sibling branches pursue).
- **perf/gc-rendertail-instrumentation** — permanent `console.log` profiling, not a fix; rationale partly inaccurate. Instrumentation-only.
- **fix/memory-list-scroll-oom** — `content-visibility:auto` is a real behavior change (scroll-anchor/Ctrl-F on off-screen items); guessed `contain-intrinsic-size`.

## Collisions / ordering (cannot both land cleanly)
- `skill-extraction-threshold` ✗ `skill-lifecycle-correctness` (contradictory defaults).
- `tool-bubble-timer-leak` (bugfix) **must precede** `tool-bubble-inplace` (refactor of same block).
- `continue-btn-weakref` depends on the eviction feature in `chathistory-gc-improvements`.
- **`.sidebar`/`.chat-history` CSS** three-way: `css-render-perf` (adds `contain:content`) ✗ `css-contain-paint` (sets `contain:layout style` — the corrective) ✗ `gpu-compositor-flicker` (removes `.sidebar` backdrop-filter).
- **`#memory-list ::after` + modal-hidden pause rule**: `brain-panel-oom` (rewrites `::after`) ✗ `memory-list-scroll-oom` ✗ `memory-panel-listener-leak` (latter two add the *identical* pause rule — duplicate).
- **`tooling/hf_url_resolver.py`**: `aria2c-downloader` (99 lines) ✗ `gguf-quality-scored` (332-line superset). File gguf second as a real merge.
- **`qtwebengine-oilpan-gc`** is a strict subset of **`agent-gc-catchup`** — **do-not-file**, ship the catch-up.

## Cross-cutting patterns a senior would flag
1. **Tests are almost all static-analysis (source-grep) assertions** — they lock code *shape*, not runtime behavior; brittle to benign refactors, catch no functional regression. Only `dom-oom-virtualization` ships a real DOM behavior test (Playwright). This is the portfolio's biggest systemic weakness. (This session added real browser tests for the history pager + a boot smoke — that's the model to extend.)
2. **Commit messages that don't match the diff** (basicsr, css-render-perf, nvidia-nim) — a senior does not ship these.
3. **Housekeeping**: unfilled `Fixes #___` placeholders (`api-token-utcnow`, `chat-auto-scroll-threshold`); stray production `console.log` in several perf branches.
4. **Unverifiable citations**: skill branches cite 2025–2026 arxiv IDs (`2504/2602/2604/2605.*`). These are *past-dated* (plausibly real), **not** fabricated — but a maintainer can't verify them; confirm each resolves or drop it.
5. **Security surface to disclose**: `qt-native-linux` opens a fixed CDP port `:9222` with `--no-sandbox`, and uses a broad `pkill -f "uvicorn app:app"` that can kill unrelated user processes — document/opt-in and kill by PID.

## Clean — PASS (senior-grade, mergeable after housekeeping)
`fix/stream-429-backoff` (best), `fix/tool-code-pycall-parsing`, `fix/provider-logo-ordering`, `fix/api-hosts-provider-gaps`, `fix/model-downloaded-detection`, `fix/gguf-quality-scored` (modulo the resolver collision), `fix/tasks-clock-repaint`, `fix/sigcache-lru-bound`, `perf/image-lazy-decode`, `fix/gpu-compositor-flicker`, `fix/css-contain-paint-transparent-rendering`, `fix/notes-quick-idle-quiescence`, `fix/research-orbit-quiescence`, `fix/timer-visibility-gating`, `fix/memory-panel-listener-leak`, `fix/brain-panel-oom`, `perf/gc-micro-improvements`, `fix/tool-bubble-timer-leak`, `perf/rewrite-streaming-renderer`, `perf/streaming-final-render`, `perf/agent-finalize-in-place`, `perf/round-finalize-inplace` (minus stray logs), `perf/smooth-typing`, `perf/hljs-deferred-highlight` (disclose FOUC), `fix/skill-agent-prompt-language`, `fix/editor-redo-shortcut`, `fix/editor-empty-save-guard`, `perf/editor-undo-compress`, `fix/untrusted-tool-result-header` (**security-sound**), `feat/catppuccin-theme`, `feat/gh-cli-detection`, `feat/agent-tool-budget`, `perf/mcp-lazy-connect`, `fix/searxng-json-docs`, `fix/pytest-timeout-dependency`, `refactor/assets-move`, `feat/ai-documentation-system` (mixed co-author attribution to clean), `feat/logging` (split diagnostics fix from instrumentation).

## Do-not-file (superseded / folded / empty)
`perf/cdp-listener-audit` (empty), `perf/rendertail-raf-throttle` (→ dom-oom-streaming-throttle), `fix/streamingtts-scope` (→ upstream #2418), `fix/agent-context-budget-discovery` (#54 → #4909), `perf/renderer-memory-reclaim` + `perf/qt-psi-graduated-reclaim` (folded into #14), `fix/qtwebengine-oilpan-gc` (subset of agent-gc-catchup), `fix/chat-history-server-paging` (develop-based, folds into #2).

---

## Remediation status (2026-07-07, post-audit)

**Verified before fixing** — I re-checked each claim against the code; two reviewer
overreaches were corrected:
- **#4661 provenance was NOT undisclosed** (the reviewer only checked commits/code
  comments). Attribution is thorough: `memory-explosion-research.md`, `active-work.md`,
  and the PR-body draft (`fix-dom-oom-virtualization.md`) all credit #4661/holden093.
  What was actually shared: the small per-node timer-teardown *idiom* in `_evictLive`
  (clear `_waveInterval`/`_elapsedTicker` + recurse), independently restructured and
  extended (`_streamRenderer`, hljs-defer). **Fix applied:** added an in-code credit
  comment at the borrow site so a diff-only reviewer sees it too.
- **Skill arxiv IDs are past-dated 2025–2026 (plausibly real), not "fabricated."**
  Reframed as *unverifiable — confirm they resolve before filing*.

**Fixed:**
- **Skills mutual-exclusion (#84 ↔ #86)** — resolved: **#84's `auto_approve_skills`
  default-flip was the contamination** (its purpose is the extraction threshold). Stripped
  all auto_approve changes from `fix/skill-extraction-threshold`; it now touches only the
  round/tool gate + confidence floor (3 files, 7 tests pass). `fix/skill-lifecycle-correctness`
  (#86) solely owns auto_approve semantics. develop unaffected (already #86 semantics).
- **longcat over-broad `except`** — narrowed to `(JSONDecodeError, AttributeError, TypeError)`
  so `function_call_to_tool_block` bugs propagate. Fixed on the branch **and develop**.
- **spinner `offsetParent`** — replaced with `getClientRects().length` (correct under
  `position:fixed`). Fixed on the branch **and develop** (+ test).

**Outstanding (verified, decided — not yet implemented):**
- **fix/basicsr-python314-compat** — commit message vs code: fix the message to say 3.13+
  (the code's actual gate), or add the advertised patch. *Bounded — message fix.*
- **fix/css-render-perf** — strip the counterproductive `will-change/translateZ/contain:content`
  additions (they contradict the stated goal and duplicate `css-contain-paint`), keep only the
  genuine cleanups. *Rework.*
- **feat/nvidia-nim-support** — split the codebase-wide `_lookup_known` ranking change out of the
  NIM data PR. *Rework.*
- **feat/aria2c-downloader** — fix remote path (runner uses the server's local script path) +
  quote `repo_id` + drop the unrelated `disable_hf_transfer` flip. *Larger; also `os.kill(pid,0)`
  Windows guard.*
- **feat/skill-quality-signals** — key the BM25 `_idf_cache` to the corpus (or recompute) to fix
  cross-corpus staleness. *Moderate.*
- **Housekeeping** — fill `Fixes #___` (`api-token-utcnow`, `chat-auto-scroll-threshold`); remove
  stray `console.log` in perf branches; drop `qtwebengine-oilpan-gc` (subset of `agent-gc-catchup`).
- **Collision ordering** unchanged (see table above): file the CSS/memory/tool-bubble/hf_url_resolver
  pairs in dependency order.
