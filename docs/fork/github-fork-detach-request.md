# GitHub Support request: re-root/detach `jdmanring/odysseus` fork network

**Problem:** `jdmanring/odysseus` shows "forked from `arcahyadi/odysseus`", which is the wrong
parent. The fork was created from the canonical upstream (`pewdiepie-archdaemon/odysseus`,
since renamed to `odysseus-dev/odysseus`, 61k+ stars). A fork-network restructuring
event (likely triggered by the upstream rename) re-rooted the network to the unrelated
4-star `arcahyadi/odysseus` repo. Verified not a security issue: no unexpected
collaborators, deploy keys, or webhooks on the fork.

**Impact:** the fork page mis-attributes the source, and the GitHub web-UI PR flow
defaults the base repo to `arcahyadi/odysseus` instead of `odysseus-dev/odysseus`.

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
`upstream` = odysseus-dev, push to upstream disabled). PRs staged via `gh` already
target `odysseus-dev` explicitly, so contribution flow is unaffected meanwhile. Just
never accept the web UI's default base repo until this is fixed.
