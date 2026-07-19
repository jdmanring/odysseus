"""Regression guard for issue #146: the aria2c launcher must stay wired.

The aria2c execution path was silently lost twice:
  - 88e1e123 deleted the _dl_base assignment (NameError on every aria2c run)
  - 247a2a35 amputated the whole launch block instead of fixing it
leaving a pre-flight that flipped a flag nothing read, while every download
silently ran hf_transfer. These are source-level wiring assertions so any
future refactor that drops a piece of the path fails loudly.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROUTES = (REPO / "routes" / "cookbook_routes.py").read_text(encoding="utf-8")
DOWNLOAD_JS = (REPO / "static" / "js" / "cookbookDownload.js").read_text(encoding="utf-8")
RUNNING_JS = (REPO / "static" / "js" / "cookbookRunning.js").read_text(encoding="utf-8")


def test_dl_base_is_assigned_before_use():
    """88e1e123 regression: _dl_base must be assigned, not just referenced."""
    assert "_dl_base = (req.local_dir.rstrip" in ROUTES
    assert ROUTES.index("_dl_base = (req.local_dir.rstrip") < ROUTES.index(
        "_bash_squote(_dl_base)"
    )


def test_launcher_builds_aria2c_command():
    """247a2a35 regression: the launch block must exist and run the script."""
    assert '"tooling" / "aria2c_download.py"' in ROUTES
    assert "hf_cmd = f\"python3 {_bash_squote(_aria2c_script)}" in ROUTES


def test_preflight_precedes_command_build():
    """The pre-flight fallback must run before hf_cmd is chosen, so a flip
    to use_aria2c=False actually selects the hf path."""
    preflight = ROUTES.index("from tooling.aria2c_download import get_aria2c")
    build = ROUTES.index('"tooling" / "aria2c_download.py"')
    assert preflight < build


def test_aria2c_path_skips_retry_loop():
    """aria2c owns resume (.aria2 sidecars); C-c pause exits non-zero and an
    outer retry loop would restart a paused download 30s later."""
    assert ROUTES.count("aria2c handles resume via .aria2 sidecar files") >= 2


def test_remote_runner_uses_scpd_tooling_path():
    """Remote hosts must invoke the scp'd copy, not the server-local path."""
    assert "~/.cookbook/tooling/aria2c_download.py" in ROUTES
    assert 'scp -O {_pf}-q -r tooling {remote}:~/.cookbook/' in ROUTES


def test_windows_targets_fall_back_to_hf():
    """The aria2c runner is a bash-quoted python3 invocation — POSIX only."""
    assert 'req.platform == "windows" or (IS_WINDOWS and not req.remote_host)' in ROUTES


def test_response_reports_actual_path():
    """The client stores the server's post-preflight decision on the task so
    cookbookRunning.js selects the matching output parser."""
    assert '"use_aria2c": bool(req.use_aria2c and not is_ollama_download)' in ROUTES
    assert "payload.use_aria2c = !!data.use_aria2c" in DOWNLOAD_JS
    assert "use_aria2c: !!data.use_aria2c" in RUNNING_JS
