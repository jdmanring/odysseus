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
| #4661-derived `?limit=400` history pagination | **#5090** DB-level history pager | Confirmed; develop uses upstream pager + our virtualization (`fix/chat-history-server-paging`). |

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
