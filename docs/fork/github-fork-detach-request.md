# GitHub Support request: re-root/detach `jdmanring/odysseus` fork network

**Problem:** `jdmanring/odysseus` shows "forked from `arcahyadi/odysseus`", which is the wrong
parent. The fork was created from the canonical upstream (`pewdiepie-archdaemon/odysseus`,
since renamed to `odysseus-dev/odysseus`, 61k+ stars). A fork-network restructuring
event (likely triggered by the upstream rename) re-rooted the network to the unrelated
4-star `arcahyadi/odysseus` repo. Verified not a security issue: no unexpected
collaborators, deploy keys, or webhooks on the fork.

**Impact: this BLOCKS the fork's entire purpose. It is not cosmetic.** GitHub scopes
cross-repository compare, and therefore pull-request creation, to the fork network. A
PR from `jdmanring/odysseus` to `odysseus-dev/odysseus` cannot be opened at all.

Measured 2026-08-02, read-only:

```sh
gh api "repos/odysseus-dev/odysseus/compare/dev...jdmanring:develop"   # 404 Not Found
gh api "repos/arcahyadi/odysseus/compare/main...jdmanring:develop"     # 200, ahead_by 1553
```

The control proves it is the network, not the history: the two repos DO share an
ancestor locally (`git merge-base upstream/dev origin/develop` resolves). Corroborating
evidence: `gh pr list --repo odysseus-dev/odysseus --author jdmanring --state all`
returns **0** — no PR has ever been filed from this account, because none could be.

The fork page also mis-attributes the source, and the web-UI PR flow defaults the base
repo to `arcahyadi/odysseus`.

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

**Correction 2026-08-02:** an earlier version of this document claimed "PRs staged via
`gh` already target `odysseus-dev` explicitly, so contribution flow is unaffected
meanwhile." That was asserted, never tested, and it is **wrong** — see the Impact
section. Targeting the base repo explicitly does not help, because the two repos are in
different fork networks. Nothing can be filed until the network is fixed or the work
moves to a fork that is genuinely in upstream's network.
