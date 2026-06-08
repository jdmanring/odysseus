# Tribal Knowledge
- **Model Picker Autohide**: The model picker hides automatically after 10 non-whitespace characters are typed to clear the UI.
- **Plan Window Desync**: The Plan Window only updates when `update_plan` is called. If the AI performs a task without calling it, the UI becomes an inaccurate reflection of the state.
- **Tmux Dependency**: The Cookbook doesn't just "start a process"; it manages remote tmux sessions. Stopping a model is a `tmux kill-session` operation.
- **CSS Variable Themes**: Themes are implemented as a set of `--bg`, `--fg`, and `--accent` variables applied to the `:root`.
