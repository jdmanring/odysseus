"""Behavioral: stopping a detached task must kill its whole process GROUP.

This is the runtime contract behind the kill-pid `group` flag and the
_tmuxGracefulKill pidfile command. A detached download/serve is a session-leader
shell whose downloader child shares its process group; a single-pid kill leaves
that child running, a group kill stops the tree. Proven here against a real
spawned tree (the codified version of the live bench proof).
"""
import os
import signal
import subprocess
import time

import pytest

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX process groups")


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _spawn_leader_with_child():
    # Mirror the detached launcher: start_new_session makes proc.pid a session +
    # process-group leader; the non-exec `sleep` runs as a child in that group.
    # The trailing `; true` defeats bash's single-command exec optimization, so
    # bash stays as the session leader and FORKS `sleep` as a child in its group
    # — the same shape as the real download tree (leader shell → child worker).
    proc = subprocess.Popen(
        ["bash", "-c", "sleep 60; true"],
        start_new_session=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    # Wait for the child sleep to appear.
    child = None
    for _ in range(50):
        r = subprocess.run(["pgrep", "-P", str(proc.pid)], capture_output=True, text=True)
        pids = [int(x) for x in r.stdout.split()]
        if pids:
            child = pids[0]
            break
        time.sleep(0.05)
    assert child is not None, "child process never spawned"
    return proc, child


def test_single_pid_kill_leaves_the_child_running():
    # The child (not our process) reflects survival cleanly; the leader is our
    # Popen child, so we reap it with wait() instead of probing its zombie pid.
    proc, child = _spawn_leader_with_child()
    try:
        assert _alive(child)
        os.kill(proc.pid, signal.SIGTERM)          # kill ONLY the leader
        proc.wait(timeout=5)                        # reap the leader
        time.sleep(0.3)
        assert _alive(child), "child (the 'downloader') survives a single-pid kill"
    finally:
        try:
            os.kill(child, signal.SIGKILL)
        except ProcessLookupError:
            pass


def test_group_kill_stops_the_whole_tree():
    proc, child = _spawn_leader_with_child()
    pgid = os.getpgid(proc.pid)                      # backend: os.getpgid
    assert os.getpgid(child) == pgid, "child shares the leader's group"
    os.killpg(pgid, signal.SIGTERM)                  # backend: os.killpg
    proc.wait(timeout=5)                             # reap the leader
    time.sleep(0.3)
    assert not _alive(child), "child dead — group kill stopped the whole tree"
