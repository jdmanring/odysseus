# Upstream Filing Guide

How to file a professional, complete upstream issue and pull request for `pewdiepie-archdaemon/odysseus`.

**James files. Agents stage.** This guide is for James to use when he is ready to submit.

---

## Part 1: Filing an Upstream Issue

### Before You File

1. Search existing issues on `pewdiepie-archdaemon/odysseus` for the bug or feature. Duplicate issues are closed without comment.
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

### PR Description Body

The PR description should have these sections in order:

#### 1. Problem

One to three paragraphs explaining what is broken or missing. Write for a reviewer who has not seen your issue. Include:
- What the user experiences (symptom)
- Root cause (if you know it)
- Reference to the upstream issue number: `Fixes #NNNN` (this auto-closes the issue on merge)

Do not start with "This PR...". Start with the problem, not the solution.

#### 2. Solution / Change

What you changed and why you chose that approach. For non-trivial changes:
- Why this approach over alternatives
- Any architectural decisions
- What you did NOT change and why (helps reviewers understand scope)

#### 3. Files Changed

A table for any PR touching more than 2 files:

```markdown
| File | Change |
|------|--------|
| `routes/auth_routes.py` | Login/logout audit logging |
| `src/log_context.py` (new) | Request correlation via contextvars |
```

#### 4. How to Test

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
- If you couldn't test on a platform, say so explicitly: "Tested on Linux (Arch, Wayland). Not tested on macOS or Windows."

**Automated tests** — if you have them, list results:
```
- [x] `pytest tests/test_foo.py` — 12 passed
- [x] `node --check static/js/affected-file.js`
```

#### 5. Screenshots

Required for any change that affects what the app looks like. See Part 3.

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

James reviewed every change, ran the tests, tested the app manually, and is the human author submitting the PR. This is no different from a developer using GitHub Copilot for code suggestions. The policy targets agents that open PRs directly without human review, not contributors who used AI as a development tool.

**When filing:**
- Do not add any AI/agent disclosure to the PR description unless a reviewer asks.
- James is the author. Write the PR in first person as James.
- If a reviewer ever asks directly: "I developed this with Claude Code as an AI assistant, but I reviewed and tested all changes myself before submitting."

---

## Part 5: Cross-Platform Notes

Odysseus runs on Linux (primary), macOS, and Windows (via PowerShell). Docker is the actively tested path. If your change could affect behavior on a platform you didn't test:

- State what you tested on: "Tested on Linux (Arch, Wayland, NVIDIA 3080). Not tested on macOS or Windows."
- For Docker-specific changes: run `docker compose config` and `docker compose up -d --build` before filing.
- For changes touching shell commands or scripts: note which shells you tested (bash, zsh, PowerShell).
- For changes to `linux_wrapper.py` or `qt-bridge.js`: Linux-only by nature — state that clearly.
- For Windows-specific code paths you can't test: describe the change and note it needs Windows verification. This is acceptable — do not omit the code because you can't test it.

---

## Part 6: Using the PR Draft Files

Every staging branch has a corresponding draft file in `docs/fork/upstream/pr-drafts/`. Each draft contains:

| Section | Purpose |
|---------|---------|
| **Title** | Ready to paste into GitHub PR title field |
| **Description** | Ready to paste into GitHub PR body (everything except the "Filing Notes" block) |
| **How to Test** | Numbered steps — should already be in the description body |
| **Filing Notes** | Internal instructions for James — **do not paste upstream** |

### Filing Workflow

1. Open the PR draft file for the branch you're filing
2. Read the **Filing Notes** section first — it may require:
   - Filing an upstream issue first (and adding its number to the `Closes #` line)
   - Capturing screenshots not yet in `docs/fork/screenshots/`
   - Referencing a related upstream PR or issue in the body
3. Complete any outstanding steps from Filing Notes
4. Open the GitHub PR form: `jdmanring/odysseus:<branch>` → `pewdiepie-archdaemon/odysseus:dev`
5. Paste the title
6. Paste the description body (everything above "Filing Notes")
7. Attach screenshots by drag-and-drop
8. Submit
9. Add the upstream PR number to `docs/fork/upstream/pr-status.md`

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
