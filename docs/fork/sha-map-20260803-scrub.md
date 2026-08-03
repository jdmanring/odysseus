# SHA map: the 2026-08-03 AI-attribution history rewrite

`develop`'s fork range (`upstream-mirror..develop`) was rewritten on 2026-08-03 to
strip AI co-authorship trailers. **A rewrite changes every SHA by construction**, so
every commit reference recorded anywhere else — docs, commit messages, issue
entries, project memory — pointed at an object that is no longer on `develop`.

This file is the translation table. It was captured immediately after the rewrite,
while the pre-rewrite objects were still reachable; once `refs/original/*` and the
backup tag are pruned, the mapping is unrecoverable.

**Pre-rewrite tip is tagged `prescrub-develop-0649d071` (pushed to origin).**

## Mapping

| old | new | commit |
|---|---|---|
| `09f86519` | `b2e97adb` | Merge upstream-mirror (25c9e735) — the 182-file ingest merge |
| `08252cd3` | `c0aee28d` | Promote the 2026-08-02 upstream ingest to develop (#171) |
| `912d3b08` | `77f62ac7` | fix(cookbook): restore upstream's repo-id provider logo |
| `65e8f3a1` | `355f58cf` | feat(tooling): merge-resolution tools for upstream ingests (#170) |
| `508b03ec` | `3b695a75` | docs(fork): close #170 — merge tooling verified on develop |
| `fa00c29f` | `31e6768f` | fix(tooling): detect add/add hunks, stop truncating the loss list |
| `46547db9` | `0cda81c3` | fix(ingest): untrack five unreferenced BSD screenshots |
| `0649d071` | `91c31113` | security(tools): adopt upstream's allowlist — $HOME not a default root |
| `aaa3f902` | `227f64a7` | docs(fork): record the upstream-loss audit |
| `579cdcc1` | `65cd4098` | docs(fork): reconcile the resume doc's internal sections |

Identity was matched on `(subject, author-date, tree)` — the rewrite preserves all
three and changes only the trailer and the parent chain. Tree is part of the key
because subject+date collide on a fork carrying duplicate history.

## The lesson, which cost real cleanup

**Rewriting history invalidates every SHA you have ever written down.** The rewrite
itself was verified carefully — tree identical, merges preserved, suite unchanged —
and then force-pushed without asking what ELSE referenced those commits. Ten SHAs
across five doc files were orphaned in one push.

Before any future rewrite: grep the docs, the issue tracker and project memory for
`[0-9a-f]{7,}`, and either capture the mapping first or plan to rewrite the
references in the same change.

## A side effect worth knowing: the rewrite HEALED duplicate history

The fork range lost 20 commits (3,045 -> 3,025 non-merges) and none of it is loss.
Those commits were mis-rooted-fork artifacts: byte-identical copies of upstream
commits under different SHAs, the same duplicate history that made the 2026-08-02
ingest a 182-file conflict. Stripping trailers made their parent chains converge,
and git deduplicated them into upstream's existing objects.

Verified on `Add admin user rename`: present once in our range before, zero after,
once in `upstream-mirror`, and upstream's copy has the identical tree `5765cf2b7`
and is an ancestor of `develop`. Sampled three more with the same result.

So the fork now shares slightly MORE history with upstream than before, and a future
ingest has marginally less duplicate surface. Not a reason to rewrite history, but
worth recording as the observed effect.
