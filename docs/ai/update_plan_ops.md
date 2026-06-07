# Tool: update_plan

## Purpose
To synchronize the AI's internal execution strategy with the user-facing Plan Window. This provides the user with real-time visibility into progress and prevents the "AI is stuck" perception.

## Input Specification
| Parameter | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `plan` | string | Yes | The full GitHub-style markdown checklist (e.g., `- [ ] Step 1`, `- [x] Step 2`). |

## Expected Output
A confirmation that the plan window has been updated.

## The "Golden Rule"
**MUST be called every single time a plan step is completed or the overall plan is revised.** 
Do NOT simply state in the chat that you have updated the plan; the UI only updates when this tool is explicitly invoked. If you are unsure if you called it in the last turn, call it again.

## Failure & Recovery
- **Error**: User reports plan is out of sync $\rightarrow$ **Recovery**: Immediately re-read the current plan and call `update_plan` with the corrected state.
- **Error**: Plan becomes too long/complex $\rightarrow$ **Recovery**: Use `update_plan` to truncate completed phases and focus on the active phase.
