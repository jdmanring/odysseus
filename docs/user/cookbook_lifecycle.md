# User Guide: Managing Models via the Cookbook

## Goal
Successfully launch a model on a GPU server and make it available for chat.

## Prerequisites
- A configured server in the Cookbook (e.g., 'gpu-box').
- Access to the model repo (e.g., HuggingFace).

## Step-by-Step Instructions
1. **Open Cookbook**: Click the `#tool-cookbook-btn` (Cookbook icon) in the tool rail.
2. **Select Model/Preset**: Either select a saved preset from the list or enter a `repo_id` for a new model.
3. **Launch**: Click **Serve Model**.
4. **Monitor Status**: 
   - The model server starts in a tmux session on the remote host.
   - Watch the "Served Models" list in the Cookbook modal. 
   - Status will transition from `Launching...` $\rightarrow$ `Ready` or `Crashed`.
5. **Select in Chat**: Once `Ready`, open the model picker in the chat interface and select the newly served model.
6. **Stop Model**: When finished, click **Stop** in the Cookbook modal to kill the tmux session and free GPU VRAM.

## Expected Result
The model appears in the chat model picker and responds to prompts.

## Troubleshooting / Tips
- **Common Issue**: Model status stays `Launching` for a long time $\rightarrow$ **Solution**: Check `tail_serve_output` in the Cookbook to see if the model is still downloading weights.
- **Common Issue**: Model crashes immediately $\rightarrow$ **Solution**: Check the logs in the Cookbook for "Out of Memory" (OOM) errors and try a smaller model or a different quantization.
- **Pro Tip**: Use `list_serve_presets` to quickly launch common configurations without typing the full command.
