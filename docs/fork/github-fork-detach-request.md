# GitHub Support request: re-root/detach `jdmanring/odysseus` fork network

> **RESOLVED 2026-08-02 — HISTORICAL RECORD, no action required.** The support ticket was
> never answered. Rather than keep waiting, the workbench moved to
> `jdmanring/odysseus-workbench`, forked directly from `odysseus-dev/odysseus` and
> verified correctly rooted, and `jdmanring/odysseus` was deleted. Everything below
> describes the retired repo and is kept because it records what happened and, more
> usefully, what was concluded wrongly along the way. Do not "update" the repo names in
> this document — it is about the old repo.

**Problem:** `jdmanring/odysseus` shows "forked from `arcahyadi/odysseus`", which is the wrong
parent. The fork was created from the canonical upstream (`pewdiepie-archdaemon/odysseus`,
since renamed to `odysseus-dev/odysseus`, 61k+ stars). A fork-network restructuring
event (likely triggered by the upstream rename) re-rooted the network to the unrelated
4-star `arcahyadi/odysseus` repo. Verified not a security issue: no unexpected
collaborators, deploy keys, or webhooks on the fork.

**Impact: unclear, and an earlier version of this document OVERCLAIMED it. Read this
section before repeating either claim.**

What is proven (2026-08-02, read-only):

```sh
# 2-part shorthand, BEFORE any jdmanring repo existed in upstream's network:
gh api "repos/odysseus-dev/odysseus/compare/dev...jdmanring:develop"          # 404
gh api "repos/arcahyadi/odysseus/compare/main...jdmanring:develop"            # 200

# 3-part explicit form, same day:
gh api "repos/odysseus-dev/odysseus/compare/dev...jdmanring:odysseus:develop" # 200, diverged
```

The 404 was the **`owner:branch` shorthand failing to resolve**, because it resolves
against the base repo's fork network and `jdmanring` had no repo in it. With the
explicit `owner:repo:branch` form, comparing the mis-rooted fork against upstream
works. So the earlier conclusion — "cross-network compare, and therefore PR creation,
is impossible" — **does not follow from this evidence and should not be repeated.**

What remains genuinely UNKNOWN: whether GitHub permits *opening a pull request* from a
repo outside the base repo's fork network. The compare API is more permissive than PR
creation, so a working compare is not proof that a PR can be filed. This cannot be
settled read-only, and filing a test PR upstream is prohibited here.

The zero-PRs-ever figure (`gh pr list --repo odysseus-dev/odysseus --author jdmanring
--state all` = 0) is weak evidence either way: nothing has been filed, but nothing was
ever declared ready either.

The fork page also mis-attributes the source, and the web-UI PR flow defaults the base
repo to `arcahyadi/odysseus` — those parts were always true and are reason enough to
fix the rooting.

**What only GitHub Support can do** (no API/CLI/settings path exists):
- **Detach** `jdmanring/odysseus` from its current fork network (makes it a standalone
  repo; preferred, since it preserves all branches, issues, and PRs), **or**
- **Re-root** it under `odysseus-dev/odysseus` if that's possible on their side.

## Submit at https://support.github.com/contact (`gh` is not supported for this; use the web form)

Suggested text:

> Subject: Fork network mis-attribution after upstream rename
>
> My repository `jdmanring/odysseus` is shown as "forked from `arcahyadi/odysseus`",
> which is incorrect. I forked from the canonical upstream (originally
> `pewdiepie-archdaemon/odysseus`, now `odysseus-dev/odysseus`). A fork-network
> restructuring appears to have re-rooted my fork to the unrelated `arcahyadi/odysseus`
> repository. Please **detach `jdmanring/odysseus` from its fork network** (I want it as
> a standalone repository), or re-root it under `odysseus-dev/odysseus` if possible. I
> have confirmed there is no security compromise on my account or repo. Please preserve
> all branches, issues, and pull requests.

## Do NOT delete + recreate

Deleting `jdmanring/odysseus` to sever the link would destroy ~100 staged PR branches,
every fork-tracker issue, and open PRs. Detach via Support preserves all of it.

## After detach: verify

```sh
gh api repos/jdmanring/odysseus --jq '{fork, parent: .parent.full_name, source: .source.full_name}'
# expect: fork=false (standalone) OR parent/source = odysseus-dev/odysseus
```

The git remotes are already correct and need no change (`origin` = jdmanring,
`upstream` = odysseus-dev, push to upstream disabled).

**Two corrections, 2026-08-02, in order:**

1. The original text claimed "PRs staged via `gh` already target `odysseus-dev`
   explicitly, so contribution flow is unaffected meanwhile." That was asserted and
   never tested.
2. It was then replaced with the opposite claim — that the mis-rooting blocks filing
   entirely — on the strength of a 404 that turned out to be a **shorthand-resolution
   artifact**, not a network block. That was worse: an untested claim replaced by a
   confidently-wrong measured-sounding one. See the Impact section.

The honest position is that **neither claim is established.** Filing may work from the
mis-rooted fork and may not; it cannot be determined without filing, which is
prohibited here.

**Resolution taken:** the workbench moved to `jdmanring/odysseus-workbench`, a fork
whose `parent` and `source` are both `odysseus-dev/odysseus`. That removes the question
entirely rather than answering it — a correctly-rooted fork is unambiguously able to
file, so the ambiguity stops mattering. The migration is justified by removing risk,
NOT by the disproven "blocked entirely" claim.
