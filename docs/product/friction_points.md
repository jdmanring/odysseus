# Odysseus Friction Points

This document identifies areas of the system where the user experience (UX) or AI operation is prone to confusion, error, or "invisible" failure.

## 1. The "Plan Sync" Gap
- **The Issue**: The Plan Window is entirely dependent on the AI calling the `update_plan` tool. 
- **The Friction**: If the AI completes a task but forgets to call the tool, the Plan Window remains stale. The user perceives this as the AI being "stuck" or ignoring the agreed-upon roadmap, leading to repetitive prompts or frustration.
- **Suggested Fix**: Implement a "heartbeat" or a mandatory check that requires a plan update at the end of every agentic loop.

## 2. Undiscoverable Interaction Patterns
- **The Issue**: The Session Rename trigger is hidden.
- **The Friction**: There is no visible "Edit" or "Rename" button. Users are expected to "just know" that clicking the session name in the header opens the rename modal.
- **Suggested Fix**: Add a small "Edit" pencil icon next to the session name.

## 3. Black-Box Skill Imports
- **The Issue**: The Skill Import URL field accepts a URL but provides no schema guidance.
- **The Friction**: If a user attempts to import a skill with an invalid format, the system may fail silently or provide a generic error, leaving the user unsure of what the correct format should be.
- **Suggested Fix**: Provide a "View Example Skill" link or a tooltip explaining the required JSON/Markdown structure.

## 4. Model Deployment Latency
- **The Issue**: The Cookbook serves models asynchronously via tmux.
- **The Friction**: After clicking "Serve Model," there is a lag before the model appears in the chat picker. Because the picker doesn't show "Loading..." or "Booting...", users may attempt to launch the model multiple times or assume it failed.
- **Suggested Fix**: Add a "Booting" status indicator to the model picker for models currently being served.

## 5. High-Risk Tooling (Bash)
- **The Issue**: The Bash Toggle allows direct system access without a confirmation step.
- **The Friction**: While powerful, the lack of a "Are you sure?" dialog for dangerous commands (e.g., `rm -rf`) creates a high-anxiety environment for users who are not comfortable with the AI's autonomy.
- **Suggested Fix**: Implement a "Confirmation Mode" for bash commands that exceed a certain risk threshold.