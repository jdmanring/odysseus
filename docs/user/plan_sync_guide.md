# User Guide: Using and Syncing the Plan Window

## Goal
Ensure that the AI's active plan is accurately reflected in the UI Plan Window to maintain transparency and trust.

## Prerequisites
- The AI must have initiated a plan using `update_plan`.

## Step-by-Step Instructions
1. **Monitor the Plan Window**: Look at the docked plan panel on the right side of the interface.
2. **Identify Desync**: If the AI says "I have updated the plan" or "Moving to the next step," but the Plan Window still shows the old checklist, a **Sync Failure** has occurred.
3. **Trigger a Manual Sync**: If the plan is desynced, prompt the AI with: *"Your plan window is out of sync. Please call `update_plan` again with the current state."*
4. **Verify Update**: Confirm the checklist items are now marked `- [x]` as described in the conversation.

## Expected Result
The Plan Window accurately mirrors the AI's internal state and progress.

## Troubleshooting / Tips
- **Common Issue**: AI updates the text in the chat but forgets to call the tool $\rightarrow$ **Solution**: Use the Manual Sync prompt mentioned in Step 3.
- **Pro Tip**: If the plan is completely wrong, you can ask the AI to "Rewrite the plan from scratch" using `update_plan`.
