# Fork‑Specific Contribution Guidelines (Odysseus Workbench)

This file **extends** the upstream `CONTRIBUTING.md`. All upstream rules still apply; the items below are **additional mandatory steps** for any contribution submitted from this fork.

---

## 0️⃣ Pre‑flight Checklist (run before starting work)

1. **Synchronise with upstream** – ensure `upstream‑mirror` and `develop` are up‑to‑date. Use the helper script `scripts/run_full_sync.sh` (see *Automation helpers* below).
2. **Search upstream for overlap** – verify that there is no open upstream issue, discussion, roadmap item, or PR that already covers the change:
   ```bash
   gh issue list --repo pewdiepie-archdaemon/odysseus --search "<short description>" --state open
   gh pr list    --repo pewdiepie-archdaemon/odysseus --search "<short description>" --state open
   ```
   **Always pass `--repo` explicitly, on reads as well as writes.** A bare `gh` command
   resolves against `gh repo set-default`, which has historically pointed at the *read‑only
   upstream* — a bare `gh issue comment 128` once posted onto upstream's unrelated PR #128,
   because both repos happened to have an item at that number and nothing errored. Reading
   the returned URL is the only tell. Writes to any owner other than `jdmanring` are now
   refused by a local `PreToolUse` guard (`~/.claude/hooks/github_write_guard.py`); reads are
   unaffected.
3. **Identify roadmap synergies** – review `docs/ROADMAP.md` for items that could be addressed with a small extension of your change. If you find a match, add a link in the PR body under “Potential roadmap impact”.

---

## 1️⃣ Cross‑platform safety

Every change must be verified on **all supported platforms** before a PR is opened:

| Platform | Verification steps |
|----------|--------------------|
| **Linux (any distro)** | Run the Docker environment (`docker compose up -d --build`) and execute the full test suite (`pytest`). |
| **macOS** | Follow the manual setup in the upstream `CONTRIBUTING.md` (Python virtual‑env, `uvicorn`). Run `pytest`. |
| **Windows** | Use the PowerShell script `launch-windows.ps1` to start the app, then run `python -m pytest`. Ensure no POSIX‑only path handling is present. |

If any platform fails, **do not open a PR** until the failure is resolved.

---

## 2️⃣ PR drafting rules (strict)

* Use the matching draft file in `docs/fork/upstream/pr‑drafts/` as the **exact** PR body.
* Append the following checklist (do **not** remove existing sections):

```
## Additional Checks Performed
- [ ] Cross‑platform test run (Linux, macOS, Windows)
- [ ] No open upstream issue/PR conflicts (search performed, links attached)
- [ ] Roadmap impact evaluated (link added if applicable)
```

All three boxes **must be ticked** before the PR can be merged.

---

## 3️⃣ Automation helpers (scripts)

All helper scripts now live in the dedicated `scripts/fork/` directory and are listed in `.gitignore` to keep them out of upstream PRs.

### How to use the helper scripts

- **`scripts/run_full_sync.sh`** – Run the full upstream‑sync pipeline. Simply execute the script from the repository root:
  ```bash
  ./scripts/fork/run_full_sync.sh
  ```
  It fetches upstream, resets `upstream‑mirror`, fast‑forwards `develop`, and rebases any open feature/fix branches onto the new `develop`.

- **`scripts/create_pr.sh <branch>`** – Open a PR for a given branch using the matching draft file. Example:
  ```bash
  ./scripts/fork/create_pr.sh feat/awesome-feature
  ```
  The script extracts the title and body from `docs/fork/upstream/pr-drafts/` and creates a PR against the `dev` base.

- **`scripts/post‑merge‑hook.sh`** – Intended to be run as a Git `post‑merge` hook. It updates `docs/fork/upstream/pr‑status.md` to mark the merged branch as *Merged* and cleans up the entry. The hook is automatically installed at `.git/hooks/post‑merge`.

---

All helper scripts now live in the dedicated `scripts/fork/` directory and are listed in `.gitignore` to keep them out of upstream PRs.


| Script | Purpose |
|--------|----------|
| `scripts/run_full_sync.sh` | Executes the full upstream‑sync pipeline: fetch upstream, reset `upstream‑mirror`, fast‑forward `develop`, and re‑base all open feature/fix branches onto the fresh `develop`. |
| `scripts/create_pr.sh <branch>` | Opens a GitHub PR for the supplied branch, automatically populating the title and body from the corresponding `docs/fork/upstream/pr‑drafts/` file and setting the base to `dev`. |
| `scripts/post‑merge‑hook.sh` | Installed as `.git/hooks/post‑merge`; automatically updates `docs/fork/upstream/pr‑status.md` to mark the PR as *Merged* and removes the branch entry. |

Each script contains a concise usage header at the top of the file.

---

## 4️⃣ Post‑merge housekeeping (automated)

The repository includes a Git **post‑merge hook** (`.git/hooks/post‑merge`) that runs `scripts/post‑merge‑hook.sh`. This keeps `pr‑status.md` in sync without manual edits.

---

## 5️⃣ Enforcement

The CI workflow now runs `scripts/validate_fork_contributing.sh`, which checks that every open PR contains the **“Additional Checks Performed”** section with all three check‑boxes ticked. PRs that fail this validation cannot be merged.

---

*All contributors (including the sole maintainer) must follow this extended checklist. It raises the quality bar above the upstream baseline and guarantees safe, cross‑platform changes.*
