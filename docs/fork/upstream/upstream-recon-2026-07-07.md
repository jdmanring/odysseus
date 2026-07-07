# Upstream Reconnaissance — 2026-07-07

Snapshot of `pewdiepie-archdaemon/odysseus` vs our staged contributions, taken
after the 320-commit ingest (upstream/dev @ `c67deaa6` / #5283; 0 new commits
since). Upstream has ~1613 open issues+PRs; this covers only items overlapping
our staged branches. **In-flight state moves — re-check the linked PRs/issues at
file time.**

## 1. Have our contributions been ingested?
**No.** We have filed nothing (agents stage; the human files). No staged branch
appears as a merged upstream PR. Where upstream independently solved the same
problem, it's listed as a supersession (§2), not an ingest.

## 2. Supersessions (our work now redundant — do NOT file)
| Ours | Superseded by (merged) | Notes |
|---|---|---|
| #54 context-budget + #57 lazy-probe research | **#4909** `read real context window for unknown proxy models` | Confirmed; develop already took upstream's tests. |
| fork `?limit=400` history pagination | maintainer commit **`45ee5a71`** (frontend `_installHistoryPager` + backend `has_more_before`) | **CORRECTED 2026-07-07:** the pager is a *maintainer direct commit* ("Polish mobile UI and editor workflows", 2026-06-27), NOT #5090. #5090 (merged, Tal.Yuan) is a route-subpackage *refactor* only. **And the pager is INERT — shadowed by a legacy route (see §8).** #4661 (OPEN, unmerged) is a *different* OOM PR (`_trimChatHistoryDOM`) — not the pager and not superseded. |

No **new** hard supersessions among merged commits. In particular, upstream
**#5033 (Gemma `<|tool_call|>` tokens)** does **not** supersede our **#35**
(`<tool_code>` python-call syntax) — different formats; both coexist on develop.

## 3. Related merged work to CITE as prior art (per the search-before-staging rule)
These landed upstream and touch our areas — reference them in the relevant PR drafts:
- **#5033** Gemma `<|tool_call|>` parser → cite in #35 (pycall) and longcat parsing (#38).
- **#4729** detect llama.cpp / label local providers → cite in #62 (`_API_HOSTS`); it's *discovery/labeling*, distinct from our host allowlist.
- **#4698** detect mistral.ai + `reasoning_effort` → cite in provider/`llm_core` work.
- **#4941 / #4704 / #4877** ReDoS-safe tool/think parser rewrites → cite in tool-parsing branches (already integrated in the develop merge).
- **#5142** webhook SSRF guard on the ntfy sender → already integrated in our `note_routes` merge.

## 4. Open PRs that overlap/conflict — coordinate before filing
| Upstream PR (open) | Overlaps our | Action |
|---|---|---|
| **#5275** parse `[bash]/[shell]/[python]` bracket-tag tool calls | tool-parsing branches | Adjacent parser work — reconcile; don't file a competing parser blindly. |
| **#5199** parse Qwen/Hermes `<tool_call>` bare-JSON (issue **#5187**) | tool-parsing (we keep Qwen markers) | Same file; coordinate/rebase around it. |
| **#5206** per-endpoint native tool-calling toggle | #60 nvidia-native-tool-calling, #62 api-hosts | Changes how native tool-calling is gated — may reframe our host-allowlist PRs. |
| **#5208** sanitize ntfy Title to ASCII (issue **#5207**) | our `note_routes` ntfy merge | Touches the same ntfy send path we instrumented. |
| **#5236** move note domain into `routes/note/` subpackage | our `note_routes.py` ntfy change | Route-refactor campaign continues — our ntfy code needs re-homing next sync. |
| **#5290 / #5158 / #5167** agent web-intent / domain / keyword hints | our `agent_loop.py` files-domain regex union | Adjacent domain-detection logic; rebase carefully. |
| **#5247** collapse thinking after completion (issue **#5239**) | our `chat.js` thinking-box merge | Same UI region; verify interaction. |
| **#5179** render Serve-tab rescan button handler expects (issue **#5178**) | our Launch-button reconciliation | **Same "wired-but-never-rendered" bug class we independently fixed.** Offer ours referencing this pattern. |
| **#5136** GGUF include-filter uses display-label quant (issue **#5137**) | #24/#29 gguf-quality-scored, model-downloaded-detection | Active bug in our GGUF area. |
| **#5219** stop Windows download orphans (issue **#5220**) | aria2c + Windows wrapper | Cookbook download reliability — adjacent. |
| **#5261/#5262**, **#5215/#5210** skill importer SSRF / SKILL.md non-ASCII | skill branches | Skill subsystem actively hardened. |

## 5. Relevant new open issues
- **#4991** *Benchmark how often the prompt-injection guard actually holds on small local models* → directly relevant to **#48**; the behavioural eval we called out-of-scope. Reference in the #48 PR.
- **#5178** rescan button wired-but-never-rendered → same class as our Launch fix.
- **#5187** Qwen/Hermes `<tool_call>` not parsed → tool-parsing.
- **#5137** GGUF fetches 0 files on display-label quant → gguf-quality-scored.
- **#4962** `_TEACHER_SYSTEM_PROMPT` import error after teacher refactor → the teacher/skill subsystem is volatile; our skill branches need re-validation against current `teacher_escalation.py`.
- **#5239** Thinking Process always visible → chat thinking UI.

## 6. Strategic takeaways for a maintainer
1. **Route-subpackage refactor is an ongoing campaign** (history/gallery/contacts/memory/research merged; **note next via #5236**). Every fork branch touching a `routes/*_routes.py` will need re-homing on each sync. Prefer landing those PRs *early*, before more refactors.
2. **Tool-parsing is a hot zone** — upstream merged the ReDoS rewrites + Gemma #5033, and has #5275/#5199 in flight. Our longcat/pycall parser branches must be rebased and reconciled against that, and filed with clear prior-art framing, or they'll read as competing.
3. **Native tool-calling gating is being reworked** (#5206). File #60/#62 with awareness that per-endpoint toggles may change the model.
4. **The "control wired but not rendered" bug class recurs** (our Launch button; upstream #5178). Worth a small shared lint/test guard if we ever land cookbook UI work upstream.
5. **#48** should cite #4991 and note the guard-benchmark as the missing behavioural validation.

## 7. ADDENDUM (2026-07-07, during #2 rebuild) — chat-history family superseded/reframed

**Recon gap caught during the #2 rebuild.** Section 4 above missed that upstream shipped
its own **server-side history pager** — `_installHistoryPager` + `_renderHistoryMessage`
in `static/js/sessions.js` (upstream `45ee5a71` "Polish mobile UI and editor workflows").
It fetches older history pages from the server on scroll-up (`_historyUrl` limit/offset,
`has_more_before`) and prepends them (`box.insertBefore`). Impact on our chat-history family:

- **`fix/chat-history-server-paging` — REDUNDANT (retire candidate).** Upstream built its
  own standalone pager independently; ours is a *different*, MessageWindow-coupled
  implementation (`serverHasMore`/`olderLoader`, 89-line content diff). No tracking record
  shows ours was ever filed → it did not land; it is superseded, not adopted. Verify with
  the human before deleting (per fork rule).

- **`fix/dom-oom-virtualization` (#2) — BLOCKED as authored; needs reframe, not rebuild.**
  The branch assumed it owned the history render + scroll path (`window.chatHistory.load()`
  replacing the render loop). Upstream now owns that path. **Crucially, upstream's pager is
  monotonic-insert — it never evicts**, so DOM node count still grows unbounded on scroll-up
  (the OOM problem virtualization exists to solve is unsolved upstream).
  - **Correct upstream PR (consolidate-down):** do NOT port the 916-line `MessageWindow`.
    Graft only a bounded-DOM eviction pass, layered on the `_installHistoryPager` added by
    maintainer commit **`45ee5a71`** (NOT #5090 — see the §2 correction). Dozens of lines that
    compose with upstream, not a class that rips out their fresh work. A maintainer accepts
    the graft; rejects the replacement.
  - **Attribution (verified against primary sources 2026-07-07):** the eviction teardown was
    written independently. The only lines resembling upstream PR **#4661**'s
    `_trimChatHistoryDOM` clear this app's own `_waveInterval`/`_elapsedTicker` timers —
    convergence forced by the shared codebase, not copied code. We rejected #4661's actual
    method as architecturally incompatible. **#4661 is OPEN and unmerged** (verified via `gh`)
    — a *different* OOM PR, not superseded by anything. So: **no in-code attribution to #4661.**
    The PR description references the maintainer's pager commit `45ee5a71` for *coordination*
    (the pager we compose with), not credit. Prior "adapted from #4661" / "#5090 pager" framing
    was wrong and is retracted.
  - **Open genuinely-strategic question (human decision):** is client-side memory-bounding
    worth an upstream PR at all, given the maintainer already shipped lazy-load (once the
    shadow is fixed) and the fork has separate renderer-OOM work (the reclaim/responsiveness stack)?

**Process lesson:** recon must grep upstream for *feature-region ownership* (who owns the
history render + scroll handler), not just named PRs/issues. A silently-merged "polish"
commit reassigned ownership of the exact code region three fork branches target.

## 8. ADDENDUM (2026-07-07, building the eviction graft) — the maintainer's history pager is inert upstream

**PROVENANCE (verified via `gh` + git, 2026-07-07 — supersedes earlier #5090 wording):**
- The history pager (frontend `_installHistoryPager`, backend `has_more_before`/limit/offset)
  was added by **maintainer direct commit `45ee5a71`** "Polish mobile UI and editor workflows"
  (pewdiepie-archdaemon, 2026-06-27). Intent: deliberate history pagination for perf/mobile.
- **#5090** (MERGED 2026-07-04, author Tal.Yuan, commit `6f6cb6ea`) = *"refactor(routes): move
  history domain into routes/history/ subpackage"* — a route move, no pager, no sessions.js.
- **#4661** (OPEN, unmerged) = *"fix(ui): prevent browser OOM during long agent interactions"*
  — a separate `_trimChatHistoryDOM` OOM attempt. Not the pager; not merged; not superseded.

While building the eviction graft (and writing its end-to-end test) I found the maintainer's
pager **does not function on current upstream** — a route-shadowing bug. `upstream-mirror` is
byte-current with `upstream/dev` (both `c67deaa6`, 0 commits behind), so this is live upstream,
proven both by route analysis AND empirically (the seeded endpoint test):

- `routes/session_routes.py` mounts with `prefix="/api"` and registers (app.py:658)
  **before** `routes/history` (app.py:687). Its legacy `GET /history/{sid}` →
  `/api/history/{sid}` ignores `limit`/`offset` and returns the full history. This legacy
  route **predates** the pager (first seen in the `e5c99a5e` base), so `45ee5a71` created the
  collision by adding the paginated route without removing the pre-existing one.
- The paginated `GET /api/history/{session_id}` (`history_routes.get_session_history`) is the
  **second** registration of the same path pattern. FastAPI matches first-registered, so the
  legacy route wins.
- Net effect: `/api/history/{id}?limit=24` returns **all** messages, no `total`, no
  `has_more_before`. The frontend pager is gated on `has_more_before`, so **it never installs**
  — scroll-up "pagination" silently renders the entire history into the DOM. The maintainer's
  pager shipped dead-on-arrival.

**Fix (staged, verified):** remove the legacy `get_history`; `get_session_history`
already serves the no-limit case via its fallback with the identical
`{role, content, metadata}` shape (== `ChatMessage.to_dict()`), so it fully
subsumes it. No-limit callers (documentLibrary, session copy/export) unaffected.
A pytest regression guard asserts the endpoint honours `?limit`.

**Staged branch `fix/chat-history-dom-eviction` (from `upstream-mirror`), 2 commits:**
1. `fix(history):` remove the shadowing legacy route — **independently valuable**
   (revives the maintainer's inert pager); candidate for its own small upstream PR.
2. `perf(history):` the eviction graft (#2 reframed) — bounds the DOM on top of the
   now-working pager; tagged-offset contiguity invariant; teardown of the app's own
   per-node handles; **no #4661 code borrowed** (see §7). Depends on commit 1.

Both verified end-to-end in real Chromium against the real server
(`tests/test_chat_history_eviction_playwright.py`): paging contiguous, DOM bounded
to the cap, eviction/refetch seam has no gap or duplicate.

**Open items for the human:** (a) issues — `fix/chat-history-dom-eviction` was cut
without a prior issue (needs one per fork rule); the route-shadowing fix needs its
own issue; #2 covers the eviction reframe. (b) whether to file the route fix as a
standalone upstream PR (recommended — it fixes a merged-but-dead feature). (c) the
marathon-from-empty session is still out of scope (documented limitation).

### §8 caveat — what the eviction graft does and does NOT claim (validated)

The seam test validates **correctness (no gap/duplicate) and a bounded live node
count** — not RSS. Frame the PR as **responsiveness + correctness on long
histories, plus a memory benefit in standard browsers**. Do NOT attach it to #2's
"prevent renderer OOM" claim: per `project_memory_oom.md`, the QtWebEngine OOM
driver is *detached* nodes + renderer cache, and in QtWebEngine an evicted node
becomes a detached node Oilpan won't reclaim without an explicit `gc()`/pressure
signal — so eviction there may convert live→detached with no RSS win. The
`perf(history)` commit message is already scoped correctly (it claims "bound the
DOM," not "fix OOM"); this note keeps the doc artifacts honest too.
