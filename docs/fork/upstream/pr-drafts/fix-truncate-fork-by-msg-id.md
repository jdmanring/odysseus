# PR Draft: fix/truncate-fork-by-msg-id -> odysseus-dev/odysseus:dev

**Branch:** `fix/truncate-fork-by-msg-id`
**Fork issue:** [#169](https://github.com/jdmanring/odysseus/issues/169) (open)
**Status:** Single clean commit `c3ec7cf7` off `upstream-mirror`, cherry-picked to develop (`d0b145e0`). File the upstream issue first, fill in `Fixes #___`, then open the PR.
**Depends on:** [#125](https://github.com/jdmanring/odysseus/issues/125) (`fix/history-route-shadow`): the paginated `/api/history` endpoint must be reachable. File #125 first.
**Related:** #2 (`fix/dom-oom-virtualization`): independent; see "Relationship" below.

---

## Upstream PR title

`fix(history): address edit/regenerate/fork by message id, not array position`

---

## Summary

### Problem

Edit, regenerate and fork compute the server-side `keep_count` from a message's
position among the currently-rendered `.msg` DOM elements
(`allMsgs.indexOf(el)`), but the server applies `keep_count` as an **absolute
index into the full, timestamp-ordered DB message list**
(`truncate_messages`: `db_messages[keep_count:]`; `fork`:
`source.history[:keep_count]`). Those two numbers are equal only when every DB
message renders as exactly one `.msg` and the DOM starts at DB index 0, which
is false whenever:

1. **The rendered set is paginated.** `/api/history` returns a tail page
   (`page_offset = max(total - page_limit, 0)`), so the first `.msg` sits at DB
   offset > 0 and `indexOf` **understates** the absolute index; truncate/fork
   cuts too early and deletes messages the user meant to keep.
2. **A message renders as several `.msg` bubbles.** A multi-round agent reply is
   one DB row but many bubbles (`.msg-continuation`), so `indexOf` **overstates**.
3. **Synthetic turns are dropped from render.** "Continue where you left off" /
   instruction turns are real DB rows with no `.msg`, so `indexOf` **understates**.

The index is pushed in both directions and depends on scroll position and
conversation shape, so no constant offset corrects it: the operation silently
truncates or forks at the wrong message. It only lines up on a short,
single-page, chat-only conversation, which is why it survives casual testing.

### Fix

Address messages by DB id, the same id `delete` already uses end to end
(`.msg` `dataset.dbId` -> server `_get_db_id` -> `session.history`).

- **Precondition.** `_db_history_entry` now stamps `meta["_db_id"] = m.id`.
  `_persist_message` serializes `meta_data` *before* stamping `_db_id` on the
  in-memory copy, so the id never round-tripped through the paginated
  `/api/history` payload; windowed/scrolled-back messages therefore had no
  `dataset.dbId`. This also **repairs delete-by-id on paginated history**, which
  was silently DOM-only before (a latent bug the same root cause produced).
- **Server.** `SessionManager.truncate_from_message(session_id, msg_id)` deletes
  the target message and everything after it, resolving the cut point by id
  **independently within each store** (the DB rows by `row.id`, the in-memory
  history by the same id set), so no positional index is shared between the two.
  `POST /truncate` accepts `from_msg_id`; `POST /fork` accepts `through_msg_id`
  (resolved within `source.history`, the list it slices).
- **Client.** `editUserMessage`, `resendUserMessage` and `regenerateFrom` send
  the user message's `dataset.dbId` as `from_msg_id`; `forkFrom` sends the AI
  message's `dataset.dbId` as `through_msg_id`. The post-cut DOM removal is
  unchanged; it correctly indexes the rendered nodes.

`keep_count` is retained as the fallback: the `/truncate N` and `/fork` **slash
commands** and the `manage_session` **AI tool** are legitimately count-based
("keep the last N") and continue to use it, and any `.msg` without a persisted
id (unpersisted/error output) falls back to it exactly as `delete` does.

### Scope

- `routes/history/history_routes.py`: `_db_history_entry` stamps `_db_id`;
  `/truncate` accepts `from_msg_id`; `/fork` accepts `through_msg_id`.
- `core/session_manager.py`: new `truncate_from_message`.
- `static/js/chat.js`: four call sites send the DB id (index kept as fallback).
- `tests/test_truncate_fork_by_msg_id.py`: new.

No response contract is narrowed: `_db_id` is **added** to `/api/history`
message metadata (the full `-k "history or truncate or fork or session"` suite,
436 passed, confirms no consumer asserted the old shape).

## Test plan

`tests/test_truncate_fork_by_msg_id.py`:
- `truncate_from_message` over a history containing a synthetic "Continue…" turn
  and a multi-round reply (the case that discriminates id- from index-based)
  asserting the exact surviving DB rows and in-memory history.
- Unknown-id truncate is a no-op (nothing deleted).
- The `_db_id` precondition, exercised through the **real** paginated
  `/api/history` endpoint (not a source assertion).
- `/fork through_msg_id` copies up to and including the target.
- A client guard that the four sites send `from_msg_id`/`through_msg_id` with
  `keep_count` retained as the fallback branch.
- Fail-red verified on the `_db_id` precondition; existing
  `test_truncate_message_count_regression` and `test_fork_session_metadata`
  remain green.

## Relationship to #2 (`fix/dom-oom-virtualization`): keep separate

This bug is **pre-existing on upstream** (upstream already paginates the DOM), so
the fix must be filable independently of the DOM-virtualization rewrite; folding
it into #2 would deny the fix to anyone who doesn't adopt the whole MessageWindow.
Verified independence: this branch is rooted on `upstream-mirror` and contains
**no** MessageWindow (`chatHistory.js` absent), yet its tests pass; the fix
references no window-layer code; and the three functions it edits are byte-
identical between `upstream-mirror` and the #2 branch (not part of #2's diff).
#2 *reduces* this bug's fresh-load blast radius but its eviction removes the
scroll-to-top recovery path: a relationship, not a merge.
