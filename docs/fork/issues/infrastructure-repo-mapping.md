# Issue: Lack of Explicit Repository Mapping Documentation

## Problem
The project lacks clear documentation distinguishing between internal and external GitHub remotes. This leads to ambiguity during the contribution process and confusion regarding where to push code.

## Impact
Contributors and agents may hesitate or push to the wrong remote, causing delays and potential security/organizational friction.

## Proposed Solution
Implement a `REMOTES.md` file in the project root or add a dedicated "Repository Mapping" section to `CONTRIBUTING.md`. This section must explicitly list:
- The purpose of each remote (e.g., `origin` = Internal Dev/User Repo, `upstream` = External Source Project).
- The expected workflow for pushing features versus syncing with the source.
