# User Journeys
## Operation: Serving a Model
1. Click `#tool-cookbook-btn` $\rightarrow$ Opens Cookbook Modal.
2. Select a model from the cached list or enter a repo ID.
3. Click "Serve" $\rightarrow$ AI executes `serve_model`.
4. Wait for "Ready" status $\rightarrow$ Model appears in the Model Picker.
5. Select the model from the Picker and start chatting.

## Operation: Modifying the AI's "Brain"
1. Click `#tool-memory-btn` $\rightarrow$ Opens Memory Modal.
2. Go to "Add" tab $\rightarrow$ Input a new fact or skill.
3. Save $\rightarrow$ AI executes `manage_memory(action='add')`.
4. Verify in "Browse" tab.
