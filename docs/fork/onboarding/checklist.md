# Odysseus Fork Onboarding Checklist

Use this checklist to verify your understanding of the Odysseus fork workflow and setup.

## Repository Setup
- [ ] Cloned the correct repository: `git@github.com:jdmanring/odysseus-workbench.git`
- [ ] Verified remotes:
  - `origin`: `github.com:jdmanring/odysseus-workbench.git` (read/write)
  - `upstream`: `github.com:odysseus-dev/odysseus.git` (read-only)
- [ ] Checked current branch: `git branch -a`
- [ ] Confirmed you're on an appropriate base branch for your work

## Documentation Review
- [ ] Read `docs/fork/README.md` (Fork Management Hub)
- [ ] Read `docs/ai/CONTEXT.md` (AI Context - Mental Model)
- [ ] Read `docs/ai/RULES.md` (Core Contribution Standards)
- [ ] Read `docs/fork/ai-policy.md` (Fork Operating Rules)
- [ ] Reviewed project architecture in `docs/project/architecture.md`
- [ ] Reviewed non-obvious behaviors in `docs/project/non-obvious-behaviors.md`

## Workflow Understanding
- [ ] Understands the difference between upstream-candidate and fork-only work
- [ ] Knows how to create branches from correct base:
  - Upstream-candidate: start from `upstream-mirror`
  - Fork-only: start from `develop`
- [ ] Understands the ingest pipeline process for upstream changes
- [ ] Knows verification protocol (Definition of Done)
- [ ] Aware of critical restrictions:
  - Never push to upstream remote
  - Never file upstream issues/PRs without authorization
  - Never modify `CONTRIBUTING.md` (it's upstream's document)

## Technical Awareness
- [ ] Knows frontend has no bundler - new JS files need `<script>` tag
- [ ] Understands Qt native app lifecycle (`qt_wrapper.py` owns server)
- [ ] Aware of QWebEngineView limitations (missing Web EyeDropper API)
- [ ] Knows download progress parsing specifics (leading space in aria2c output)
- [ ] Understands non-native tool results are wrapped via `untrusted_context_message()` in `src/prompt_security.py` (role=user, metadata.trusted=False)
- [ ] Aware that `data/settings.json` overrides `DEFAULT_SETTINGS`

## Verification Steps
If this is your first time setting up:
- [ ] Successfully built and ran the application (Docker or native)
- [ ] Created a test session and sent a message
- [ ] Verified basic chat functionality works
- [ ] Confirmed you can access settings and modify preferences

## Contribution Readiness
- [ ] Have a tracking entry for your work in `docs/fork/issues/` (GitHub Issues are disabled on the workbench by design)
- [ ] Know how to update fork tracking documents when work is ready:
  - PR draft in `docs/fork/upstream/pr-drafts/`
  - `docs/fork/active-work.md`
  - `docs/fork/upstream/pr-status.md`
  - `docs/fork/changes-from-upstream.md`
- [ ] Understands squashing staging branches before upstream PR
- [ ] Knows how to rebase staging branches on `upstream-mirror`

## Completion
- [ ] Felt confident explaining the fork's purpose to another contributor
- [ ] Can distinguish between documentation that belongs upstream vs. fork-only
- [ ] Knows where to find procedures for common operations (ingest, rebase, cherry-pick)
