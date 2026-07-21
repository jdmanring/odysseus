# Upstream Filing Guide

How to file a professional, complete upstream issue and pull request from a contribution workbench.

**You file. Agents stage.** This guide is for the human author when they are ready to submit.

---

## Part 1: Filing an Upstream Issue

### Before You File

1. Search existing issues on `odysseus-dev/odysseus` for the bug or feature. Duplicate issues are closed without comment.
2. Check `docs/fork/upstream/pr-status.md` — if a staging branch already fixes the bug, you can skip the issue and file the PR directly (include a clear problem statement in the PR body).
3. Verify the fix is not already in `upstream-mirror` — run `git diff upstream-mirror develop -- <relevant file>` to confirm.

### Bug Issue Template

```
**Install method:** Docker | manual Python | WSL | native

**OS / device:** [e.g. "Artix Linux, Wayland, NVIDIA open drivers" or "macOS 14.4, M1 MacBook Pro" or "Windows 11, RTX 4080"]

**Browser (if applicable):** Chrome 124 | Firefox 125 | Safari 17 | n/a (Docker)

**Steps to Reproduce:**
1. [First action]
2. [Second action]
3. [What you observe]

**Expected:** [What should have happened]

**Actual:** [What actually happened]

**Logs / Error Output:**
```
[paste relevant log lines or console errors here]
```

**Additional context:** [anything else — GPU type, model backend, token state, etc.]
```

**Rules for bug issues:**
- Steps must be numbered and exact. "It doesn't work" is not a step.
- Paste the actual error text, not a paraphrase.
- For model-serving issues, include: backend (Ollama/vLLM/llamacpp/etc.), model name, GPU/CPU and OS.
- For Cookbook issues, include: what model was being downloaded, local vs remote, whether a HF token was set.

### Enhancement / Feature Request Template

```
**Area:** [Cookbook | Chat | Email | Search | Settings | other]

**Problem / Motivation:**
[What gap or pain point does this address? Be specific — "it would be nice" is not a motivation.]

**Proposed Solution:**
[What would you add, change, or remove? What does the user experience look like after this change?]

**Alternatives Considered:**
[What else did you consider? Why did you rule it out?]
```

### Issue Title Conventions

- Bug: `[Component] Short description of the broken behavior` — e.g. `[Cookbook] Download crashes on SSL error mid-transfer`
- Feature: `[Component] What you want to add` — e.g. `[Cookbook] Add pause/resume for model downloads`
- Keep it under 80 characters.
- Do not start with "Bug:" or "Feature:" — the issue type is visible from the label.

---

## Part 2: Filing an Upstream Pull Request

### Before You File

Go through this checklist before opening the GitHub PR form:

- [ ] Branch starts from `upstream-mirror` (not `develop`) — verify: `git log --oneline upstream-mirror..fix/branch-name`
- [ ] Single clean commit — `git log --oneline upstream-mirror..fix/branch-name` shows exactly 1 commit (or a small set of tightly related commits)
- [ ] Diff contains only intended files — `git diff upstream-mirror..fix/branch-name --name-only`
- [ ] No hardcoded paths, usernames, or tokens in the diff
- [ ] All tests pass locally — `python -m pytest` (or equivalent)
- [ ] For UI changes: screenshots captured and ready to attach (see Part 3)
- [ ] The upstream issue has been filed and you have its number (if one was required — check Filing Notes in the PR draft)
- [ ] Read the **Filing Notes** section of the PR draft — it has branch-specific instructions

### PR Title

Use [Conventional Commits](https://www.conventionalcommits.org) format:

```
type(scope): short imperative summary
```

Common types: `fix`, `feat`, `refactor`, `docs`, `test`, `chore`, `ci`

Examples:
- `fix(chat): hoist streamingTTS to fix ReferenceError in catch block`
- `feat(cookbook): aria2c parallel download system with real-time progress UI`
- `docs: AI-first documentation system — universal hub-and-spoke onboarding`

Keep the title under 72 characters. Put the "why" in the body, not the title.

### PR Base Branch

**Always target `dev`, not `main`.** The GitHub form may default to `main` — change it. PRs against `main` are redirected or closed.

### PR Description Bot

The upstream repo runs an automated bot (`pr-description-check-bot`) on every new PR. It auto-comments and flags missing or empty sections. PRs that don't clear the bot are often closed by maintainers without review. The bot checks for:

- **`## Summary`** — must exist and be non-empty ("describe what changed and why")
- **`## Linked Issue`** — must contain `Fixes #NNN`, a bare `#NNN`, or an issue URL
- **`## Type of Change`** — at least one box must be checked
- **`## Checklist`** — the duplicate-search box must be checked
- **`## How to Test`** — must contain real detail ("a sentence or two, not just 'tested locally'")

The bot does not check `## Target branch` or `## Visual / UI changes` but reviewers do.

**All PR draft files already include these sections pre-filled.** Paste the draft body and the bot will pass.

### PR Description Sections (in order)

#### 1. Summary (bot-required)

One to two paragraphs explaining what changed and why — written for a reviewer who hasn't seen your issue.

#### 2. Target Branch

`- [x] This PR targets **\`dev\`**, not \`main\`.` — pre-checked in all drafts.

#### 3. Linked Issue (bot-required)

`Fixes #NNN` — fill in the upstream issue number. The bot rejects a bare `Fixes #`. If filing the PR without a corresponding issue, reference a related discussion with `Related: #NNN`.

#### 4. Type of Change (bot-required)

Check at least one box. Pre-checked correctly in all draft files.

#### 5. Detail Sections (optional but recommended for non-trivial PRs)

Detail sections go between Type of Change and Checklist. Common subheadings:

**Problem:** What the user experiences, root cause, symptom. Do not start with "This PR...".

**Solution / Change:** What you changed and why this approach over alternatives. Note explicitly what you did NOT change and why.

**Files Changed:** A table for any PR touching more than 2 files:

```markdown
| File | Change |
|------|--------|
| `routes/auth_routes.py` | Login/logout audit logging |
| `src/log_context.py` (new) | Request correlation via contextvars |
```

#### 6. Checklist (bot-required)

Pre-checked in all draft files. The bot specifically checks the duplicate-search box:

```markdown
- [x] I searched open issues and open PRs — this is not a duplicate.
- [x] This PR targets `dev`
- [x] My changes are limited to the scope described above.
- [x] I actually ran the app and verified the change works end-to-end.
```

#### 7. How to Test (bot-required)

**Required.** A PR without test steps will be sent back.

Format: numbered steps, starting from a defined state. Write so that a reviewer who has never seen your fix can follow them cold.

```markdown
### How to Test

1. Clone the repo and start the server: `docker compose up -d --build` or `uvicorn app:app`
2. [Action that triggers the change]
3. [What you should observe]
4. [Optional: verify the old broken behavior is gone — how to confirm the before-state would have failed]
```

**Rules:**
- Must describe running the actual app, not just `pytest`. Unit test results are supporting evidence, not a substitute.
- Cover the golden path (the fix works) and the regression path (the old behavior is gone).
- For backend-only changes: include the API call or UI action that exercises the changed path.
- For frontend-only changes: describe the exact user interaction and what the before/after looks like.
- For bug fixes: include how to reproduce the original bug without the patch (even just in prose), so reviewers understand what changed.
- If you couldn't test on a platform, say so explicitly: "Tested on Artix Linux, Wayland, NVIDIA open drivers. Not tested on macOS or Windows."

**Automated tests** — if you have them, list results:
```
- [x] `pytest tests/test_foo.py` — 12 passed
- [x] `node --check static/js/affected-file.js`
```

#### 8. Visual / UI changes

Required for any UI-touching PR (full checklist). For non-UI PRs, just say "None — no HTML, CSS, or DOM-writing JS was changed." See Part 3 for requirements.

---

## Part 3: Screenshots

### What Requires a Screenshot

Any change that affects these files or areas **must** include a screenshot:
- `static/style.css`
- `static/index.html`
- Any `static/js/*.js` file that writes to the DOM, modifies classes, or controls visibility
- New routes that serve HTML or are accessed from the UI
- Any button, modal, dropdown, card, panel, badge, or color change

If you're unsure whether your change is "visual," treat it as visual and attach a screenshot. Reviewers are instructed to close UI PRs without screenshots.

### What the Screenshot Must Show

- The running app, not a mockup or editor preview
- The changed element in context (not a cropped-out fragment)
- For modifications to existing UI: both before and after (two screenshots, labeled)
- For new UI elements: the element in its natural location in the app
- If the change affects mobile layout: add a mobile screenshot (browser DevTools → responsive mode, or a real device)

### How to Attach

Drag and drop images into the GitHub PR description text box. Do not link to files in your fork repo — upstream reviewers may not have access. GitHub stores the image on its CDN and renders it inline.

### Screenshot Notes in PR Drafts

PR draft files note which screenshots are needed:
- `Screenshot: docs/fork/screenshots/<name>.png` — the screenshot exists locally; attach it
- `Screenshots: (To be captured before filing)` — capture before opening the PR form

Never file a UI PR with "screenshots pending" — the PR will be sent back.

---

## Part 4: The LLM Agent Note

CONTRIBUTING.md contains this warning:

> **Auto-generated PRs.** If you are running an LLM agent (Devin, Cursor, OpenHands, Claude Code, etc.) against this repo: please open an issue describing the problem first instead of opening a PR directly. Bulk agent-generated PRs that don't match the project's visual style or contribution format will be closed without review, even when the underlying fix is correct.

**This applies to unreviewed bulk submissions — not to work developed with AI assistance.**

You reviewed every change, ran the tests, tested the app manually, and are the human author submitting the PR. This is no different from a developer using GitHub Copilot for code suggestions. The policy targets agents that open PRs directly without human review, not contributors who used AI as a development tool.

**When filing:**
- Do not add any AI/agent disclosure to the PR description unless a reviewer asks.
- You are the author. Write the PR in first person.
- If a reviewer ever asks directly: "I developed this with AI coding assistance, but I reviewed and tested all changes myself before submitting."

---

## Part 5: Cross-Platform Notes

Odysseus runs on Linux (primary), macOS, and Windows (via PowerShell). Docker is the actively tested path. If your change could affect behavior on a platform you didn't test:

- State what you tested on: "Tested on Linux (Arch, Wayland, NVIDIA 3080). Not tested on macOS or Windows."
- For Docker-specific changes: run `docker compose config` and `docker compose up -d --build` before filing.
- For changes touching shell commands or scripts: note which shells you tested (bash, zsh, PowerShell).
- For changes to `qt_wrapper.py` or `qt-bridge.js`: Linux-only by nature — state that clearly.
- For Windows-specific code paths you can't test: describe the change and note it needs Windows verification. This is acceptable — do not omit the code because you can't test it.

---

## Part 6: Using the PR Draft Files

### PR Drafts

Every staging branch has a corresponding draft file in `docs/fork/upstream/pr-drafts/` (one file per branch, named with `/` replaced by `-`). Each draft contains:

| Section | Purpose |
|---------|---------|
| **Proposed title** | Ready to paste into GitHub PR title field |
| **Description body** | Everything between the title and "Filing Notes" — paste this into the GitHub PR body |
| **Filing Notes** | Internal instructions — **do not paste upstream** |

The description body is pre-filled with all 8 required PR template sections (Summary, Target branch, Linked Issue, Type of Change, detail sections, Checklist, How to Test, Visual / UI changes). Paste it directly and the upstream PR template bot will pass.

### Issue Drafts

Branches whose Filing Notes say "File upstream issue first" have a corresponding issue draft in `docs/fork/upstream/issue-drafts/`. This is a **separate file** from the PR draft — it contains the upstream issue title and body pre-written and ready to paste into GitHub's new issue form on `odysseus-dev/odysseus`.

**Issue draft format:**

```
# Upstream Issue Draft: <name>

**File on:** `odysseus-dev/odysseus`
**Related PR draft:** docs/fork/upstream/pr-drafts/<name>.md
**Branch:** <branch-name>
**Type:** Bug | Enhancement | Refactor

---

## Title

`[exact title to paste into GitHub]`

---

## Body

[complete issue body — paste into the GitHub new-issue text box]
```

The body uses the upstream bug or feature request template, fully filled out — not a skeleton. For bugs: Install method, OS/device, Steps to Reproduce, Expected, Actual, Logs, Additional context. For features: Area, Problem/Motivation, Proposed Solution, Alternatives Considered.

**Every PR draft needs a new upstream issue filed on `odysseus-dev/odysseus` before the PR is opened.** The issue draft for each branch lives in `docs/fork/upstream/issue-drafts/<name>.md`.

Even when a related upstream issue already exists (filed by someone else, or covering a broader topic), file a new issue for your specific PR. The new issue should describe your contribution's scope and approach precisely. Reference the existing issue in the body — `Related to #NNN` or `Addresses the [specific aspect] described in #NNN` — but use `Fixes #` on your own new issue, not on someone else's.

The upstream CONTRIBUTING.md and its LLM agent policy both require opening an issue before opening a PR. There are no exceptions.

All active PR drafts have `Fixes # <!-- [file upstream issue first] -->` and a corresponding issue draft file.

### Filing Workflow

**Step 1 — If the PR draft says "file upstream issue first":**

1. Open `docs/fork/upstream/issue-drafts/<name>.md`
2. Go to `https://github.com/odysseus-dev/odysseus/issues/new`
3. Paste the **Title** from the issue draft into the title field
4. Paste the **Body** from the issue draft into the body field
5. Submit and note the issue number assigned
6. Open `docs/fork/upstream/pr-drafts/<name>.md` and replace `Fixes # <!-- [file upstream issue first] -->` with `Fixes #NNN`

**Step 2 — File the PR:**

1. Open the PR draft file for the branch
2. Read **Filing Notes** — confirm issue number is filled in and screenshots are ready
3. Open: `<your-fork>:<branch>` → `odysseus-dev/odysseus:dev`
4. Paste the proposed title
5. Paste the description body (everything above "Filing Notes")
6. Attach screenshots by drag-and-drop
7. Submit
8. Add the upstream PR number to `docs/fork/upstream/pr-status.md`

---

## Part 7: Common Mistakes That Get PRs Closed

| Mistake | Consequence | Fix |
|---------|-------------|-----|
| No "How to Test" section | PR sent back | Write numbered steps from a cold start |
| UI change without screenshot | PR closed | Capture and attach before filing |
| PR opened against `main` instead of `dev` | Maintainer redirects or closes | Change base branch before submitting |
| Issue not filed first (when required) | Reviewer asks for it | Check Filing Notes; file issue, add its # to PR |
| Vague problem description ("it doesn't work") | Closed as not actionable | Write exact symptoms and steps to reproduce |
| Upstream issue already exists / PR already open | Duplication | Search before filing; link to existing instead |
| Mixing unrelated changes in one PR | Hard to review; rejected | One fix per PR; split if needed |
| Screenshot links to fork repo files | Reviewer can't see it | Drag-and-drop into GitHub text box |
| "This PR adds X" title style | Weak title | Imperative: "add X" not "adds X" |
| AI-disclosure boilerplate in PR body | Looks bot-generated | Write naturally, first-person, no disclosure |
