"""Serving a model must work on a POSIX host without tmux (e.g. a real Mac).

model_serve was tmux-gated on every non-Windows local host, so serving failed
on a stock Mac. It now uses the same detached-process + logfile model as the
download path on local-POSIX-without-tmux; only REMOTE POSIX still needs tmux.
The serve log tee was also hardcoded to /tmp/odysseus-tmux — wrong on macOS,
where the session dir is under $TMPDIR and the poller reads it there.

Verified on the Tahoe bench with a stand-in server (the VM has no GPU for a
real model): `python3 -m http.server` launched detached, logged to the real
session dir, bound its port, and group-killed clean. Real model serving needs
GPU hardware; this proves the launch/log/stop infrastructure.
"""
from pathlib import Path

ROUTES = (Path(__file__).resolve().parent.parent / "routes" / "cookbook_routes.py"
          ).read_text(encoding="utf-8")


def _serve_region():
    # From the serve tmux precheck to its detached dispatch.
    start = ROUTES.index("Remote Windows Diffusers serving is not supported")
    end = ROUTES.index("_launch_local_detached(session_id, runner_lines)")
    return ROUTES[start - 400:end + 60]


def test_serve_uses_local_detached_not_just_windows():
    region = _serve_region()
    assert "local_detached = (not remote) and (IS_WINDOWS or not _tmux_ok)" in ROUTES
    assert "if not is_windows and not local_detached and not _tmux_ok:" in region
    # The launch/shell/exit decisions key off local_detached now.
    assert "keep_shell_open=not local_detached" in region
    assert "if local_detached:" in region


def test_serve_log_uses_real_session_dir_not_hardcoded_tmp():
    # No hardcoded /tmp/odysseus-tmux in the tee/mkdir COMMANDS (broke macOS
    # serve logging); the log dir is derived from TMUX_LOG_DIR instead.
    assert "tee -a /tmp/odysseus-tmux" not in ROUTES
    assert 'mkdir -p /tmp/odysseus-tmux' not in ROUTES
    assert "_serve_log_dir = TMUX_LOG_DIR.as_posix()" in ROUTES


def test_serve_crash_watchdog_skips_detached():
    # The tmux capture-pane watchdog must punt for a detached serve (no pane).
    assert "local_detached_serve = (not remote) and (is_windows or (TMUX_LOG_DIR" in ROUTES


def test_windows_specific_serve_handling_kept():
    # local_windows must remain for genuinely Windows-only command handling
    # (llama.cpp PATH), not be blanket-replaced by local_detached.
    assert "llama.cpp/build-cuda/bin/Release" in ROUTES
    assert "if local_windows:" in ROUTES
