"""Stopping a detached local download/serve must kill the whole process tree.

A detached task (macOS/Windows, or any local host without tmux) has no tmux
session to signal — its leader pid is in <session>.pid and the download/serve
child is in the same process group. Stop must therefore kill the GROUP, not a
single pid, or the child keeps running orphaned.

- Backend: /api/cookbook/kill-pid grows a `group` flag → os.getpgid + os.killpg
  on LOCAL POSIX. Verified live on the Tahoe bench: an aria2c download's
  python+aria2c children died on a group kill (single-pid kill left them).
- Frontend: _tmuxGracefulKill's local-POSIX command reads <session>.pid and
  kills its process group (and still runs tmux kill-session so a tmux-launched
  local task also stops). Windows already tears down the tree via Stop-Tree.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROUTES = (REPO / "routes" / "cookbook_routes.py").read_text(encoding="utf-8")
RUNNING_JS = (REPO / "static" / "js" / "cookbookRunning.js").read_text(encoding="utf-8")


def test_kill_pid_has_group_flag():
    assert "group: bool = False" in ROUTES


def test_kill_pid_group_uses_killpg_on_local_posix():
    assert "elif req.group and not host:" in ROUTES
    assert "os.getpgid(req.pid)" in ROUTES
    assert "os.killpg(pgid" in ROUTES
    # Keep the <100 guard on the derived group id too.
    assert "Refusing to signal process group" in ROUTES


def test_status_exposes_detached_pid():
    assert "detached_pid = task_pid" in ROUTES
    assert '"pid": detached_pid,' in ROUTES


def test_graceful_kill_local_posix_kills_process_group():
    # The local (non-Windows, non-remote) branch must derive the pgid from the
    # pidfile and kill the group, not just tmux.
    assert 'P=$(cat "$D/${sid}.pid"' in RUNNING_JS
    assert 'ps -o pgid= -p "$P"' in RUNNING_JS
    assert 'kill -TERM "-$G"' in RUNNING_JS
    # Still attempts tmux so a tmux-launched local task also stops.
    assert "tmux kill-session -t ${sid}" in RUNNING_JS


def test_windows_stop_is_tree_kill():
    # Regression guard: Windows detached stop must remain a recursive tree kill.
    assert "function Stop-Tree" in RUNNING_JS
