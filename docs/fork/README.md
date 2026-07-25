# docs/fork: Fork Management Hub

This directory is the source of truth for everything that makes this fork different
from the upstream project, and for tracking our work as contributors.

---

## What This Fork Is

**Upstream:** `github.com/odysseus-dev/odysseus` (remote: `upstream`)
**This fork:** `github.com/jdmanring/odysseus` (remote: `origin`)

Odysseus is a self-hosted AI workspace. This fork is a personal AI stack
on KDE/Artix Linux. The goals are:

1. Run a full-featured local AI workspace on Linux with native desktop integration
2. Contribute improvements and bug fixes back to the upstream project over time

This fork adds Linux-native capabilities (Qt native wrapper, GPU acceleration,
crash recovery) and a high-performance model download stack, none of which exist
upstream. It also tracks upstream bugs and prepares PRs for upstreaming fixes.

---

## Navigation

| Want to know... | File |
|----------------|------|
| What's different in this fork vs. upstream? | `changes-from-upstream.md` |
| What's being worked on right now? | `active-work.md` |
| What bugs and issues are open? | `issue-tracker.md` |
| How to send work upstream? | `upstream/how-to-contribute.md` |
| Status of all staged upstream PRs? | `upstream/pr-status.md` |
| Upstream bugs we've discovered? | `upstream/bug-discoveries.md` |
| Per-PR staged draft docs? | `upstream/drafts/` |
| Work staying fork-only (not upstream)? | `fork-only/` |
| Build and install the Linux app? | `linux-build-and-install.md` |
| Fork change history? | `fork-changelog.md` |

---

## Two Remotes, One Rule

- `origin`: This fork. Normal dev target. Push freely.
- `upstream`: The source project. **Never push, file issues, or open PRs here
  without explicit per-action authorization.** Stage work in `upstream/drafts/`
  and file them yourself.
