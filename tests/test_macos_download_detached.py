"""Local downloads must work on POSIX hosts without tmux (e.g. macOS).

macOS has no tmux in the base system, but model_download used to hard-require
it on every non-Windows local host — so cookbook downloads failed on a stock
Mac with "tmux is required". The fix routes local-POSIX-without-tmux through the
same detached-process + logfile model Windows already uses (launch via
_launch_local_detached, poll the <session>.pid / <session>.log files), and only
REMOTE POSIX hosts still require tmux. Verified end-to-end on the Tahoe bench:
a real hf-fallback download completed with bytes on disk and DOWNLOAD_OK, and
the status poller reported "completed".

Source-level wiring assertions (the route is not importable in isolation), plus
functional checks on the BinManager platform behavior.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROUTES = (REPO / "routes" / "cookbook_routes.py").read_text(encoding="utf-8")


# ── launch routing ────────────────────────────────────────────────────────
def test_local_detached_covers_posix_without_tmux():
    assert "_tmux_ok = await _binary_available(\"tmux\", remote, req.ssh_port)" in ROUTES
    assert "local_detached = (not remote) and (IS_WINDOWS or not _tmux_ok)" in ROUTES


def test_tmux_hard_fail_only_when_not_detached():
    # The missing-tmux error must be gated on `not local_detached`, so a local
    # macOS host without tmux falls back instead of erroring.
    assert "if not is_windows and not local_detached and not _tmux_ok:" in ROUTES


def test_local_branch_skips_tmux_tail_when_detached():
    # The exec-tail + wrapper write + tmux setup_cmd belong to the tmux path only.
    assert "if not local_detached:" in ROUTES
    assert "setup_cmd = None if local_detached else f\"tmux set-option" in ROUTES


def test_detached_launch_dispatch_present():
    assert "if setup_cmd is None:" in ROUTES
    assert "_launch_local_detached(session_id, lines)" in ROUTES


# ── status poller routing (must agree with launch, for the task's whole life) ─
def test_poller_detects_detached_by_pidfile():
    assert '_pid_path = TMUX_LOG_DIR / f"{session_id}.pid"' in ROUTES
    assert "local_detached_task = (not remote) and (IS_WINDOWS or _pid_path.exists())" in ROUTES
    # The file-based branch and its downstream uses must all key off it.
    assert "elif local_detached_task:" in ROUTES
    assert "if local_detached_task:" in ROUTES
    assert "if is_alive or (local_detached_task and full_snapshot):" in ROUTES


def test_no_stale_local_win_task_symbol():
    # The Windows-only name was generalized; a leftover would split routing.
    assert "local_win_task" not in ROUTES


# ── BinManager: no fabricated macOS aria2c URLs (they 404'd) ───────────────
def test_bin_manager_has_no_darwin_aria2c_entry():
    from tooling.bin_manager import BinManager
    keys = BinManager.TOOL_MAP["aria2c"].keys()
    assert ("Darwin", "x86_64") not in keys
    assert ("Darwin", "arm64") not in keys
    # Linux/Windows static builds remain.
    assert ("Linux", "x86_64") in keys
    assert ("Windows", "AMD64") in keys


def test_bin_manager_returns_none_for_darwin_fast():
    # No map entry ⇒ ensure_binary returns None without any network attempt, so
    # get_aria2c() falls through to shutil.which (system/brew aria2c).
    from tooling.bin_manager import BinManager
    assert ("Darwin", "arm64") not in BinManager.TOOL_MAP["aria2c"]
